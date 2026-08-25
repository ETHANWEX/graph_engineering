"use strict";

(() => {
  const main = document.getElementById("main");
  const status = document.getElementById("connection-status");
  if (!(main instanceof HTMLElement) || !(status instanceof HTMLElement)) return;

  const identity = (prefix) => `${prefix}-${crypto.randomUUID()}`;
  const setStatus = (message) => { status.textContent = message; };
  let mutationActive = false;

  const submit = async (form) => {
    if (mutationActive) return;
    mutationActive = true;
    const data = Object.fromEntries(new FormData(form).entries());
    let endpoint = form.dataset.endpoint;
    if (form.dataset.geForm === "action") {
      endpoint = `/api/v1/runs/${encodeURIComponent(form.dataset.runId)}/actions/${encodeURIComponent(data.action)}`;
      data.content = `${data.action} ${form.dataset.runId}: ${data.content}`;
      delete data.action;
    }
    if (!endpoint) return;
    if (Object.hasOwn(data, "contract_revision")) data.contract_revision = Number(data.contract_revision);
    data.message_id ??= identity("message-ui");
    data.confirmation_message_id ??= identity("message-confirm-ui");
    data.request_id = identity("request-ui");
    data.idempotency_key = data.request_id;
    setStatus("Submitting through the Human Gateway…");
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data),
      });
      if (!response.ok) throw new Error("mutation rejected");
      setStatus("Persisted response received; refreshing authoritative state.");
      location.reload();
    } catch (_error) {
      setStatus("Action was not applied or could not be confirmed. Refresh authoritative state.");
      mutationActive = false;
    }
  };

  for (const form of document.querySelectorAll("form[data-ge-form]")) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void submit(form);
    });
  }

  let pollActive = false;
  let etag = null;
  const poll = async () => {
    if (pollActive || mutationActive || document.hidden) return;
    pollActive = true;
    try {
      const headers = etag === null ? {} : {"If-None-Match": etag};
      const response = await fetch("/api/v1/project", {
        method: "GET", credentials: "same-origin", cache: "no-store", headers,
      });
      if (response.status === 304) {
        setStatus("Live authoritative state is current.");
        return;
      }
      if (!response.ok) throw new Error("poll rejected");
      etag = response.headers.get("ETag");
      const snapshot = await response.json();
      const source = snapshot.source;
      if (!source || source.snapshot_id !== main.dataset.snapshotId || source.instance_id !== main.dataset.instanceId) {
        setStatus("Authoritative state changed; refreshing full snapshot.");
        location.reload();
        return;
      }
      setStatus("Live authoritative state is current.");
    } catch (_error) {
      setStatus("Disconnected or stale. Reconnecting from a full authoritative snapshot.");
      etag = null;
    } finally {
      pollActive = false;
    }
  };
  setInterval(() => { void poll(); }, 5000);
})();

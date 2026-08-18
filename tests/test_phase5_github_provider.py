import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from graph_engineering.delivery import (
    CheckConclusion,
    GitHubChecksMonitor,
    GitHubChecksProvider,
    GitHubProviderError,
    GitHubProviderErrorKind,
    GitHubRepository,
    PullRequestContent,
    PullRequestManager,
    PullRequestSpec,
    ReviewVerdict,
    render_pull_request_body,
)
from graph_engineering.runtime import StateStore
from graph_engineering.verifier.http_pipeline import HttpResponse


class Transport:
    def __init__(self, responses: list[HttpResponse | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def request(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse:
        copied = dict(headers)
        self.calls.append((method, url, copied, body))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def response(payload: object, status: int = 200, **headers: str) -> HttpResponse:
    return HttpResponse(status, headers, json.dumps(payload).encode())


def repo() -> GitHubRepository:
    return GitHubRepository(owner="acme", name="service", api_base_url="https://api.github.test")


def test_checks_bind_exact_repository_and_sha_and_preserve_conclusions() -> None:
    sha = "a" * 40
    transport = Transport(
        [
            response(
                {
                    "check_runs": [
                        {
                            "id": 9,
                            "head_sha": sha,
                            "status": "completed",
                            "conclusion": "timed_out",
                            "html_url": "https://github.test/check/9",
                        }
                    ]
                }
            )
        ]
    )
    provider = GitHubChecksProvider(repo(), transport=transport, allowed_hosts=("api.github.test",))
    status = provider.status(sha)
    assert status.checks[0].conclusion is CheckConclusion.TIMED_OUT
    assert status.successful is False

    mismatch = Transport(
        [
            response(
                {
                    "check_runs": [
                        {
                            "id": 9,
                            "head_sha": "b" * 40,
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ]
                }
            )
        ]
    )
    with pytest.raises(GitHubProviderError) as exc:
        GitHubChecksProvider(repo(), transport=mismatch, allowed_hosts=("api.github.test",)).status(
            sha
        )
    assert exc.value.kind is GitHubProviderErrorKind.IDENTITY


def test_checks_classify_auth_rate_limit_and_unknown_without_code_failure() -> None:
    for status, headers, kind in [
        (401, {}, GitHubProviderErrorKind.AUTH),
        (403, {"x-ratelimit-remaining": "0"}, GitHubProviderErrorKind.RATE_LIMIT),
    ]:
        provider = GitHubChecksProvider(
            repo(),
            transport=Transport([response({}, status, **headers)]),
            allowed_hosts=("api.github.test",),
        )
        with pytest.raises(GitHubProviderError) as exc:
            provider.status("a" * 40)
        assert exc.value.kind is kind


def test_checks_query_resumes_after_runtime_restart_without_write_side_effect(
    tmp_path: Path,
) -> None:
    sha = "a" * 40
    state = StateStore(tmp_path / "state.db")
    initial = GitHubChecksProvider(
        repo(), transport=Transport([]), allowed_hosts=("api.github.test",)
    )
    query_id = GitHubChecksMonitor(state, initial).start("run-1", sha)
    transport = Transport(
        [
            response(
                {
                    "check_runs": [
                        {
                            "id": 1,
                            "head_sha": sha,
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ]
                }
            )
        ]
    )
    recovered = GitHubChecksMonitor(
        state,
        GitHubChecksProvider(repo(), transport=transport, allowed_hosts=("api.github.test",)),
    )
    assert recovered.poll(query_id).successful is True
    assert recovered.get(query_id)["commit_sha"] == sha
    assert [call[0] for call in transport.calls] == ["GET"]


def test_pr_intent_handle_recovery_barrier_and_secret_safety(tmp_path: Path) -> None:
    created = {
        "number": 12,
        "html_url": "https://github.test/acme/service/pull/12",
        "node_id": "PR_12",
        "head": {"ref": "phase/run-1"},
        "base": {"ref": "main"},
    }
    transport = Transport([response([]), response(created, 201)])
    state = StateStore(tmp_path / "state.db")
    manager = PullRequestManager(
        state,
        repo(),
        transport=transport,
        token="top-secret",
        allowed_hosts=("api.github.test",),
        can_write=lambda: True,
    )
    spec = PullRequestSpec(
        run_id="run-1", base="main", head="phase/run-1", title="Delivery", body="safe"
    )
    first = manager.ensure(spec)
    second = PullRequestManager(
        state,
        repo(),
        transport=Transport([]),
        token="top-secret",
        allowed_hosts=("api.github.test",),
        can_write=lambda: True,
    ).ensure(spec)
    assert first == second
    assert len(transport.calls) == 2
    assert "top-secret" not in str(state.outbox_rows())

    blocked = PullRequestManager(
        state,
        repo(),
        transport=Transport([]),
        allowed_hosts=("api.github.test",),
        can_write=lambda: False,
    )
    with pytest.raises(GitHubProviderError, match="barrier"):
        blocked.ensure(spec.model_copy(update={"run_id": "run-2", "head": "phase/run-2"}))


def test_uncertain_pr_create_stops_and_restart_never_posts_again(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    spec = PullRequestSpec(
        run_id="run-1", base="main", head="phase/run-1", title="Delivery", body="safe"
    )
    first = Transport([response([]), OSError("socket closed after write")])
    manager = PullRequestManager(
        state,
        repo(),
        transport=first,
        allowed_hosts=("api.github.test",),
        can_write=lambda: True,
    )
    with pytest.raises(GitHubProviderError) as exc:
        manager.ensure(spec)
    assert exc.value.kind is GitHubProviderErrorKind.UNCERTAIN_EFFECT
    recovery = Transport([response([])])
    with pytest.raises(GitHubProviderError) as recovered:
        PullRequestManager(
            state,
            repo(),
            transport=recovery,
            allowed_hosts=("api.github.test",),
            can_write=lambda: True,
        ).ensure(spec)
    assert recovered.value.kind is GitHubProviderErrorKind.UNCERTAIN_EFFECT
    assert [call[0] for call in recovery.calls] == ["GET"]


def test_pr_body_contains_complete_delivery_evidence_sections() -> None:
    body = render_pull_request_body(
        PullRequestContent(
            contract_revision=3,
            run_id="run-1",
            requirement_matrix_summary="2 verified; 1 unverified",
            verifier_ci_summary="Verifier passed; CI pending",
            review_summary="Security approved; test adequacy blocked",
            review_verdict=ReviewVerdict.BLOCKED,
            unverified=("production GitHub E2E",),
            external_effects=("PR #12 created",),
            risks=("CI remains pending",),
            final_report_refs=("sha256:" + "a" * 64,),
            reproduction_commands=("python -m pytest",),
        )
    )
    for heading in (
        "Contract and Run",
        "Requirement Matrix",
        "Verifier and CI",
        "Review",
        "Unverified",
        "External Effects",
        "Risks",
        "Final Report and Artifacts",
        "Reproduction",
    ):
        assert heading in body

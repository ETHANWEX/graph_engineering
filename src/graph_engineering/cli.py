"""Phase 0 command-line interface."""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError

from .contracts import ContractRepository, RunPlanner
from .conversation import ConversationRepository, IntentCompiler
from .discovery import DiscoveryRepository, DiscoveryService, DiscoveryState
from .models import ExecutionGraph, HumanMessage
from .runtime import StateStore
from .schema import export_schemas

app = typer.Typer(help="Graph Engineering protocol tools.", no_args_is_help=True)
graph_app = typer.Typer(help="Static Execution Graph tools.", no_args_is_help=True)
schema_app = typer.Typer(help="JSON Schema tools.", no_args_is_help=True)
verifier_app = typer.Typer(help="Dynamic Verifier lifecycle tools.", no_args_is_help=True)
service_app = typer.Typer(help="Local Runtime Service lifecycle.", no_args_is_help=True)
qualification_app = typer.Typer(
    help="Versioned integration qualification evidence.", no_args_is_help=True
)
app.add_typer(graph_app, name="graph")
app.add_typer(schema_app, name="schema")
app.add_typer(verifier_app, name="verifier")
app.add_typer(service_app, name="service")
app.add_typer(qualification_app, name="qualification")


@qualification_app.command("collect")
def qualification_collect(
    output: Annotated[Path, typer.Option("--output", "-o", dir_okay=False)],
    project_root: Annotated[
        Path, typer.Option("--project-root", exists=True, file_okay=False, resolve_path=True)
    ] = Path("."),
) -> None:
    """Collect read-only local identity and an honest default claim matrix."""

    from graph_engineering.qualification import QualificationRepository, collect_local_evidence

    repository = QualificationRepository(output)
    try:
        repository.write(collect_local_evidence(project_root, external_authorized=False))
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(str(output))


@qualification_app.command("report")
def qualification_report(
    evidence: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Read an existing evidence document without rewriting it or touching Runtime state."""

    from graph_engineering.qualification import QualificationRepository

    document = QualificationRepository(evidence).read()
    typer.echo(document.model_dump_json())


@service_app.command("start")
def service_start(
    project_root: Annotated[
        Path, typer.Option("--project-root", exists=True, file_okay=False, resolve_path=True)
    ] = Path("."),
    project_id: Annotated[str, typer.Option("--project-id")] = "project",
) -> None:
    """Run the single-project Runtime Service in the foreground."""

    from graph_engineering.service import RuntimeService

    RuntimeService(project_root, project_id).serve()


@service_app.command("status")
def service_status(
    project_root: Annotated[
        Path, typer.Option("--project-root", exists=True, file_okay=False, resolve_path=True)
    ] = Path("."),
) -> None:
    """Read Runtime Service health and version compatibility."""

    from graph_engineering.service import ServiceClient

    typer.echo(json.dumps(ServiceClient(project_root).call("health"), sort_keys=True))


@service_app.command("stop")
def service_stop(
    project_root: Annotated[
        Path, typer.Option("--project-root", exists=True, file_okay=False, resolve_path=True)
    ] = Path("."),
) -> None:
    """Request authenticated controlled shutdown."""

    from graph_engineering.service import ServiceClient

    typer.echo(json.dumps(ServiceClient(project_root).call("shutdown"), sort_keys=True))


@app.command("mcp-server")
def mcp_server_command(
    project_root: Annotated[
        Path, typer.Option("--project-root", exists=True, file_okay=False, resolve_path=True)
    ] = Path("."),
) -> None:
    """Serve the strict Graph Engineering MCP control surface over stdio."""

    from graph_engineering.mcp_server import run_mcp_server

    run_mcp_server(project_root)


def _delivery_paths(run_id: str, state_db: Path | None) -> tuple[Path, Path, Path]:
    database = state_db or Path(".ge") / "runs" / run_id / "state.db"
    root = database.parent
    return database, root / "artifacts", root / "reports"


def _fixture_boundaries(project_root: Path, run_id: str) -> tuple[Any, Any]:
    """Build deterministic in-process boundaries explicitly labelled as fixture evidence."""

    from graph_engineering.models.common import ArtifactKind
    from graph_engineering.models.results import (
        ExecutorResult,
        ExecutorStatus,
        VerifierResult,
        VerifierStatus,
    )
    from graph_engineering.runtime import ArtifactStore, FakeExecutor, FakeVerifier

    control = StateStore(project_root / ".ge" / "control" / "phase3.db")
    with control.read_connection() as connection:
        row = connection.execute(
            "SELECT graph_json FROM planned_runs WHERE run_id=?", (run_id,)
        ).fetchone()
    if row is None:
        raise typer.BadParameter("prepared Run was not found")
    graph = ExecutionGraph.model_validate_json(str(row["graph_json"]))
    git = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "--verify", "HEAD^{commit}"],
        text=True,
        capture_output=True,
        check=False,
        shell=False,
    )
    if git.returncode != 0:
        raise typer.BadParameter("deterministic Git fixture requires a real local Git repository")
    diff = subprocess.run(
        ["git", "-C", str(project_root), "diff", "--binary", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
        shell=False,
    )
    if diff.returncode != 0:
        raise typer.BadParameter("deterministic Git fixture could not read the local diff")
    patch = ArtifactStore(project_root / ".ge" / "runs" / run_id / "artifacts").put_bytes(
        diff.stdout.encode("utf-8"), media_type="text/x-diff", kind=ArtifactKind.PATCH
    )

    def success() -> ExecutorResult:
        return ExecutorResult(
            schema_version="1.0",
            status=ExecutorStatus.SUCCEEDED,
            summary="deterministic fixture",
        )

    scripts = {
        node.node_id: [success() for _ in range(4)]
        for node in graph.nodes
        if node.node_type.value != "verifier"
    }
    if "deliver" in scripts:
        scripts["deliver"] = [
            ExecutorResult(
                schema_version="1.0",
                status=ExecutorStatus.SUCCEEDED,
                summary=f"deterministic local Git fixture at {git.stdout.strip()}",
                artifacts=[patch],
            )
        ]
    executor = FakeExecutor(scripts)
    verifier = FakeVerifier(
        {
            node.node_id: [
                VerifierResult(
                    schema_version="1.0",
                    status=VerifierStatus.PASSED,
                    summary="deterministic fixture passed",
                )
                for _ in range(4)
            ]
            for node in graph.nodes
            if node.node_type.value == "verifier"
        }
    )
    return executor, verifier


@app.command("run")
def run_prepared(
    run_id: str,
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    idempotency_key: Annotated[str | None, typer.Option("--idempotency-key")] = None,
    deterministic_fixture: Annotated[bool, typer.Option("--deterministic-fixture")] = False,
) -> None:
    """Explicitly start a prepared durable Run (fixture provider is visibly opt-in)."""

    if not deterministic_fixture:
        raise typer.BadParameter(
            "this checkout requires an explicitly configured executor; "
            "--deterministic-fixture is test evidence, not real Codex/GitHub E2E"
        )
    from graph_engineering.delivery import AutonomousDeliveryCoordinator

    root = project_root.resolve()
    executor, verifier = _fixture_boundaries(root, run_id)
    result = AutonomousDeliveryCoordinator(root, executor=executor, verifier=verifier).run(
        run_id,
        request_id=request_id or f"request:{uuid.uuid4()}",
        idempotency_key=idempotency_key or f"run-start:{run_id}",
    )
    typer.echo(json.dumps(result.__dict__, sort_keys=True))


@app.command("status")
def status_run(
    run_id: str,
    state_db: Annotated[Path | None, typer.Option("--state-db")] = None,
    watch: Annotated[bool, typer.Option("--watch")] = False,
) -> None:
    """Read a persisted Runtime status snapshot; watch emits one bounded snapshot per invocation."""

    database, _, _ = _delivery_paths(run_id, state_db)
    state = StateStore(database)
    with state.read_connection() as connection:
        run = connection.execute(
            "SELECT run_id,project_id,status,barrier,current_node_id,terminal_reason,updated_at "
            "FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise typer.BadParameter("Run was not found")
        nodes = [
            dict(row)
            for row in connection.execute(
                "SELECT node_id,status,attempt_count FROM nodes WHERE run_id=? ORDER BY node_id",
                (run_id,),
            )
        ]
    typer.echo(json.dumps({"run": dict(run), "nodes": nodes, "watch": watch}, sort_keys=True))


def _control_run(run_id: str, action: str, state_db: Path | None) -> None:
    from graph_engineering.models import ControlReason, StateChangeControlIntent
    from graph_engineering.models.control import (
        ControlReasonCode,
        StateChangeAction,
        Urgency,
    )
    from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime

    database, _, _ = _delivery_paths(run_id, state_db)
    state = StateStore(database)
    with state.read_connection() as connection:
        row = connection.execute(
            "SELECT graph_json,contract_hash FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
    if row is None:
        raise typer.BadParameter("Run was not found")
    runtime = GraphRuntime(database.parent, executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.recover(
        run_id,
        ExecutionGraph.model_validate_json(str(row["graph_json"])),
        str(row["contract_hash"]),
    )
    intent = StateChangeControlIntent(
        schema_version="1.0",
        intent_kind="state_change",
        intent_id=f"cli:{action}:{uuid.uuid4()}",
        source_message_id=f"cli-message:{uuid.uuid4()}",
        actor_id="human",
        project_id="project",
        run_id=run_id,
        action=StateChangeAction(action),
        reason=ControlReason(schema_version="1.0", code=ControlReasonCode.HUMAN_REQUEST),
        urgency=Urgency.IMMEDIATE,
        confidence=1.0,
        requires_confirmation=False,
    )
    typer.echo(runtime.control(intent).model_dump_json())


@app.command("pause")
def pause_run(
    run_id: str, state_db: Annotated[Path | None, typer.Option("--state-db")] = None
) -> None:
    _control_run(run_id, "pause", state_db)


@app.command("resume")
def resume_run(
    run_id: str, state_db: Annotated[Path | None, typer.Option("--state-db")] = None
) -> None:
    _control_run(run_id, "resume", state_db)


@app.command("interrupt")
def interrupt_run(
    run_id: str, state_db: Annotated[Path | None, typer.Option("--state-db")] = None
) -> None:
    _control_run(run_id, "interrupt", state_db)


@app.command("cancel")
def cancel_run(
    run_id: str, state_db: Annotated[Path | None, typer.Option("--state-db")] = None
) -> None:
    from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime

    database, _, _ = _delivery_paths(run_id, state_db)
    runtime = GraphRuntime(database.parent, executor=FakeExecutor(), verifier=FakeVerifier())
    with runtime.state.read_connection() as connection:
        row = connection.execute(
            "SELECT graph_json,contract_hash FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
    if row is None:
        raise typer.BadParameter("Run was not found")
    runtime.recover(
        run_id,
        ExecutionGraph.model_validate_json(str(row["graph_json"])),
        str(row["contract_hash"]),
    )
    runtime.cancel(run_id)
    typer.echo(json.dumps({"run_id": run_id, "status": "cancelled"}, sort_keys=True))


@app.command("report")
def report_run(
    run_id: str,
    state_db: Annotated[Path | None, typer.Option("--state-db")] = None,
    live: Annotated[bool, typer.Option("--live")] = False,
) -> None:
    """Read the latest immutable delivery-report revision without mutation."""

    from graph_engineering.delivery import DeliveryReportCompiler
    from graph_engineering.runtime import ArtifactStore

    database, artifacts, reports = _delivery_paths(run_id, state_db)
    if live:
        with StateStore(database).read_connection() as connection:
            row = connection.execute(
                "SELECT run_id,status,barrier,current_node_id,updated_at FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise typer.BadParameter("Run was not found")
        typer.echo(json.dumps(dict(row), sort_keys=True))
    else:
        bundle = DeliveryReportCompiler(
            StateStore(database), ArtifactStore(artifacts), reports
        ).latest(run_id)
        typer.echo(bundle.model_dump_json())


@app.command("accept")
def accept_run(
    run_id: str,
    state_db: Annotated[Path | None, typer.Option("--state-db")] = None,
    report_revision: Annotated[int, typer.Option("--report-revision", min=1)] = 1,
    actor_id: Annotated[str, typer.Option("--actor-id")] = "human",
    project_id: Annotated[str, typer.Option("--project-id")] = "project",
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
) -> None:
    """Record confirmed Human acceptance; this never merges."""

    from graph_engineering.delivery import HumanDecisionService

    database, _, _ = _delivery_paths(run_id, state_db)
    human = _human_message(
        f"confirm accept {run_id}", actor_id=actor_id, project_id=project_id, run_id=run_id
    )
    if state_db is None:
        from graph_engineering.delivery import AutonomousDeliveryCoordinator
        from graph_engineering.runtime import FakeExecutor, FakeVerifier

        record = AutonomousDeliveryCoordinator(
            project_root.resolve(), executor=FakeExecutor(), verifier=FakeVerifier()
        ).decide("accept", human, report_revision=report_revision)
    else:
        record = HumanDecisionService(StateStore(database)).accept(
            human, report_revision=report_revision
        )
    typer.echo(record.model_dump_json())


@app.command("reject")
def reject_run(
    run_id: str,
    reason: Annotated[str, typer.Option("--reason", min=1)],
    state_db: Annotated[Path | None, typer.Option("--state-db")] = None,
    report_revision: Annotated[int, typer.Option("--report-revision", min=1)] = 1,
    actor_id: Annotated[str, typer.Option("--actor-id")] = "human",
    project_id: Annotated[str, typer.Option("--project-id")] = "project",
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
) -> None:
    """Record confirmed Human rejection and append a Contract revision."""

    from graph_engineering.delivery import HumanDecisionService

    database, _, _ = _delivery_paths(run_id, state_db)
    human = _human_message(
        f"confirm reject {run_id}: {reason}",
        actor_id=actor_id,
        project_id=project_id,
        run_id=run_id,
    )
    if state_db is None:
        from graph_engineering.delivery import AutonomousDeliveryCoordinator
        from graph_engineering.runtime import FakeExecutor, FakeVerifier

        record = AutonomousDeliveryCoordinator(
            project_root.resolve(), executor=FakeExecutor(), verifier=FakeVerifier()
        ).decide("reject", human, reason=reason, report_revision=report_revision)
    else:
        record = HumanDecisionService(StateStore(database)).reject(
            human, reason=reason, report_revision=report_revision
        )
    typer.echo(record.model_dump_json())


@app.command("revise")
def revise_run(
    run_id: str,
    reason: Annotated[str, typer.Option("--reason", min=1)],
    state_db: Annotated[Path | None, typer.Option("--state-db")] = None,
    report_revision: Annotated[int, typer.Option("--report-revision", min=1)] = 1,
    actor_id: Annotated[str, typer.Option("--actor-id")] = "human",
    project_id: Annotated[str, typer.Option("--project-id")] = "project",
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
) -> None:
    """Append a Human revision decision and immutable successor lineage."""

    from graph_engineering.delivery import HumanDecisionService

    database, _, _ = _delivery_paths(run_id, state_db)
    human = _human_message(
        f"confirm revise {run_id}: {reason}",
        actor_id=actor_id,
        project_id=project_id,
        run_id=run_id,
    )
    if state_db is None:
        from graph_engineering.delivery import AutonomousDeliveryCoordinator
        from graph_engineering.runtime import FakeExecutor, FakeVerifier

        record = AutonomousDeliveryCoordinator(
            project_root.resolve(), executor=FakeExecutor(), verifier=FakeVerifier()
        ).decide("revise", human, reason=reason, report_revision=report_revision)
    else:
        record = HumanDecisionService(StateStore(database)).revise(
            human, reason=reason, report_revision=report_revision
        )
    typer.echo(record.model_dump_json())


def _write_immutable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(
                f"immutable control artifact already exists with other content: {path}"
            )
        return
    path.write_text(content, encoding="utf-8")


def _human_message(
    content: str,
    *,
    actor_id: str,
    project_id: str,
    run_id: str | None,
) -> HumanMessage:
    return HumanMessage(
        schema_version="1.0",
        message_id=f"message:{uuid.uuid4()}",
        actor_id=actor_id,
        project_id=project_id,
        run_id=run_id,
        content=content,
        created_at=datetime.now(UTC),
    )


@app.command("start")
def start_conversation(
    project_root: Annotated[
        Path, typer.Option("--project-root", exists=True, file_okay=False, resolve_path=True)
    ] = Path("."),
    conversation_id: Annotated[str, typer.Option("--conversation-id")] = "project-main",
    project_id: Annotated[str, typer.Option("--project-id")] = "project",
    actor_id: Annotated[str, typer.Option("--actor-id")] = "human",
    message: Annotated[str | None, typer.Option("--message", "-m")] = None,
) -> None:
    """Start or resume the persistent Human Control Conversation."""

    root = project_root.resolve()
    control_root = root / ".ge" / "control"
    state = StateStore(control_root / "phase3.db")
    conversations = ConversationRepository(state)
    discovery_repository = DiscoveryRepository(state)
    discovery = DiscoveryService(discovery_repository)
    contracts = ContractRepository(state)
    planner = RunPlanner(state)
    try:
        conversation = conversations.get(conversation_id)
    except KeyError:
        conversation = conversations.create(conversation_id, project_id, actor_id)

    def process(content: str) -> bool:
        nonlocal conversation
        human = _human_message(
            content,
            actor_id=conversation.actor_id,
            project_id=conversation.project_id,
            run_id=conversation.active_run_id,
        )
        current = discovery_repository.latest_for_conversation(conversation_id)
        if (
            current is not None
            and current.state is DiscoveryState.AWAITING_CONFIRMATION
            and current.draft is not None
            and any(token in content.casefold() for token in ("confirm", "确认", "同意"))
        ):
            conversations.append(conversation_id, human)
            draft_id = contracts.stage(conversation_id, current.draft)
            frozen = contracts.freeze(draft_id, human)
            discovery.mark_frozen(current.session_id, frozen.contract)
            planned = planner.create(conversation.project_id, frozen)
            conversations.set_active_run(conversation_id, planned.run_id)
            conversation = conversations.get(conversation_id)
            contract_path = (
                control_root
                / "contracts"
                / (
                    f"{frozen.contract.contract_id.replace(':', '-')}-"
                    f"r{frozen.contract.revision}.json"
                )
            )
            graph_path = control_root / "graphs" / f"{planned.run_id.replace(':', '-')}.json"
            lock_path = (
                control_root
                / "acceptance"
                / f"{frozen.acceptance_lock.lock_id.replace(':', '-')}.json"
            )
            _write_immutable(contract_path, frozen.contract.canonical_json() + "\n")
            _write_immutable(graph_path, planned.graph.canonical_json() + "\n")
            _write_immutable(
                lock_path,
                json.dumps(
                    frozen.acceptance_lock.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            typer.echo(
                f"Contract r{frozen.contract.revision} frozen; acceptance lock created; "
                f"Execution Graph prepared as {planned.run_id}. "
                "Autonomous execution has not started."
            )
            return True
        if current is not None and current.state is DiscoveryState.AWAITING_ANSWERS:
            conversations.append(conversation_id, human)
            updated = discovery.answer(current.session_id, human)
            if updated.draft is None:
                typer.echo(discovery.next_question(updated.session_id))
            else:
                typer.echo("Contract draft is ready. Review summary:")
                typer.echo(updated.draft.canonical_json())
                typer.echo(
                    "Risk/permission summary: no undeclared network or secrets; "
                    "auto-merge is false. "
                    "Type 'confirm' to freeze, or provide a revision."
                )
            return False
        compiled = IntentCompiler().compile(human, active_run_id=conversation.active_run_id)
        if compiled.intent is not None:
            conversations.append(conversation_id, human)
            typer.echo(compiled.intent.canonical_json())
            if compiled.intent.requires_confirmation:
                typer.echo("This action requires explicit confirmation before Runtime mutation.")
            return False
        conversations.append(conversation_id, human)
        started = discovery.start(conversation_id, human, root)
        typer.echo(discovery.next_question(started.session_id))
        return False

    if message is not None:
        process(message)
        return
    typer.echo(f"Conversation {conversation_id} ready. Enter 'exit' to close the frontend.")
    while True:
        try:
            content = typer.prompt("Human")
        except (EOFError, KeyboardInterrupt):
            typer.echo()
            return
        if content.strip().casefold() in {"exit", "quit"}:
            return
        process(content)


def _load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


@verifier_app.command("list")
def verifier_list() -> None:
    """List registered MVP Verifier types."""

    from graph_engineering.verifier import builtin_registry

    for verifier_type in builtin_registry().types():
        typer.echo(verifier_type)


@verifier_app.command("validate")
def verifier_validate(
    path: Path,
    state_db: Annotated[
        Path | None, typer.Option(help="Optionally stage validation evidence.")
    ] = None,
    source: Annotated[Path | None, typer.Option()] = None,
    tests: Annotated[Path | None, typer.Option()] = None,
    fixtures: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Validate a Verifier Manifest without executing it."""

    from pydantic import ValidationError

    from graph_engineering.verifier import VerifierManifest

    try:
        manifest = VerifierManifest.model_validate(_load_document(path))
    except (OSError, ValueError, ValidationError) as exc:
        typer.echo(f"Invalid Verifier Manifest: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"Valid Verifier Manifest: {manifest.verifier_id} r{manifest.revision} "
        f"({manifest.verifier_type})"
    )
    if state_db is not None:
        if source is None or tests is None:
            raise typer.BadParameter("--source and --tests are required with --state-db")
        from graph_engineering.runtime import StateStore
        from graph_engineering.verifier import VerifierLifecycle, VerifierRepository

        repository = VerifierRepository(StateStore(state_db))
        repository.stage(manifest, source=source, tests=tests, fixtures=fixtures)
        repository.record(
            manifest.verifier_id,
            manifest.revision,
            VerifierLifecycle.VALIDATED,
            {"passed": True, "command": "ge verifier validate"},
        )


@verifier_app.command("permissions")
def verifier_permissions(path: Path) -> None:
    """Render the exact Human permission summary used before freeze."""

    from graph_engineering.verifier import VerifierManifest, VerifierRepository

    manifest = VerifierManifest.model_validate(_load_document(path))
    typer.echo(VerifierRepository.permission_summary(manifest))


def _lifecycle_evidence(
    state_db: Path, verifier_id: str, revision: int, evidence: Path, lifecycle: str
) -> None:
    from graph_engineering.runtime import StateStore
    from graph_engineering.verifier import VerifierLifecycle, VerifierRepository

    result = _load_document(evidence)
    if not isinstance(result, dict):
        raise typer.BadParameter("evidence must be a JSON/YAML object")
    repository = VerifierRepository(StateStore(state_db))
    repository.record(verifier_id, revision, VerifierLifecycle(lifecycle), dict(result))
    typer.echo(f"Verifier {verifier_id} r{revision} recorded {lifecycle} evidence")


@verifier_app.command("test")
def verifier_test(state_db: Path, verifier_id: str, revision: int, evidence: Path) -> None:
    """Record passed deterministic test evidence for a validated revision."""

    _lifecycle_evidence(state_db, verifier_id, revision, evidence, "tested")


@verifier_app.command("dry-run")
def verifier_dry_run(state_db: Path, verifier_id: str, revision: int, evidence: Path) -> None:
    """Record passed isolated dry-run evidence for a tested revision."""

    _lifecycle_evidence(state_db, verifier_id, revision, evidence, "dry_run")


@verifier_app.command("freeze")
def verifier_freeze(
    state_db: Path,
    verifier_id: str,
    revision: int,
    contract_id: str,
    contract_revision: int,
    confirmation_message_id: str,
) -> None:
    """Freeze a dry-run revision after explicit Human confirmation."""

    from graph_engineering.runtime import StateStore
    from graph_engineering.verifier import VerifierRepository

    hashes = VerifierRepository(StateStore(state_db)).freeze(
        verifier_id,
        revision,
        contract_id=contract_id,
        contract_revision=contract_revision,
        confirmation_message_id=confirmation_message_id,
    )
    typer.echo(hashes.model_dump_json())


def _format_location(location: tuple[int | str, ...]) -> str:
    result = ""
    for part in location:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += ("." if result else "") + part
    return result or "document"


@graph_app.command("validate")
def validate_graph(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate an Execution Graph without executing any node."""

    try:
        document = _load_document(file)
        ExecutionGraph.model_validate(document)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        typer.echo(f"document: invalid JSON/YAML: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(f"file: could not read input: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except ValidationError as exc:
        typer.echo(f"Invalid Execution Graph ({len(exc.errors())} error(s)):", err=True)
        for error in exc.errors(include_url=False):
            location = _format_location(error["loc"])
            typer.echo(f"- {location}: {error['msg']}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Valid Execution Graph: {file}")


@schema_app.command("export")
def export_schema_command(
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path("schemas"),
) -> None:
    """Export stable schemas for all public Phase 0 models."""

    paths = export_schemas(output)
    typer.echo(f"Exported {len(paths)} schemas to {output}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

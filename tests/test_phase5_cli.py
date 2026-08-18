from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from graph_engineering.cli import app
from graph_engineering.delivery import DeliveryReportCompiler
from graph_engineering.runtime import ArtifactStore, StateStore

runner = CliRunner()


def terminal_database(tmp_path: Path) -> Path:
    database = tmp_path / "run-1" / "state.db"
    state = StateStore(database)
    state.migrate()
    with state.transaction() as connection:
        connection.execute(
            "INSERT INTO delivery_terminal_fixtures("
            "run_id,contract_id,contract_revision,status,reason,created_at) "
            "VALUES ('run-1','contract-1',1,'succeeded','completed',?)",
            (datetime.now(UTC).isoformat(),),
        )
    return database


def test_report_accept_reject_cli_use_versioned_runtime_services(tmp_path: Path) -> None:
    database = terminal_database(tmp_path)
    state = StateStore(database)
    DeliveryReportCompiler(
        state,
        ArtifactStore(database.parent / "artifacts"),
        database.parent / "reports",
    ).compile("run-1")
    with state.read_connection() as connection:
        before = (
            connection.execute("SELECT COUNT(*) FROM delivery_report_revisions").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0],
        )
    report = runner.invoke(app, ["report", "run-1", "--state-db", str(database)])
    assert report.exit_code == 0, report.output
    assert '"revision":1' in report.output
    with state.read_connection() as connection:
        after = (
            connection.execute("SELECT COUNT(*) FROM delivery_report_revisions").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0],
        )
    assert after == before
    accept = runner.invoke(
        app,
        ["accept", "run-1", "--state-db", str(database), "--report-revision", "1"],
    )
    assert accept.exit_code == 0, accept.output
    assert '"merge_performed":false' in accept.output
    reject = runner.invoke(
        app,
        [
            "reject",
            "run-1",
            "--state-db",
            str(database),
            "--reason",
            "missing boundary",
        ],
    )
    assert reject.exit_code == 0, reject.output
    assert '"new_contract_revision":2' in reject.output

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from graph_engineering.cli import app


def invoke(root: Path, content: str) -> Any:
    return CliRunner().invoke(
        app,
        [
            "start",
            "--project-root",
            str(root),
            "--conversation-id",
            "conversation-1",
            "--message",
            content,
        ],
    )


def test_ge_start_recovers_multi_turn_discovery_and_does_not_start_implementer(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    first = invoke(tmp_path, "Add a greeting endpoint")
    assert first.exit_code == 0
    assert "test command" in first.output.lower()

    answers = (
        "python -m pytest",
        "GET /greeting returns hello",
        "No interface changes",
        "Follow existing Python style",
        "No network or secrets",
        "report only",
        "one hour and 20 calls",
    )
    for answer in answers:
        result = invoke(tmp_path, answer)
        assert result.exit_code == 0
    assert "Contract draft is ready" in result.output

    database = tmp_path / ".ge" / "control" / "phase3.db"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM acceptance_locks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM planned_runs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM executor_sessions").fetchone()[0] == 0

    confirmed = invoke(tmp_path, "I explicitly confirm this Contract")
    assert confirmed.exit_code == 0
    assert "Autonomous execution has not started" in confirmed.output
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM acceptance_locks").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM planned_runs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM executor_sessions").fetchone()[0] == 0
        assert connection.execute("SELECT state FROM discovery_sessions").fetchone()[0] == "frozen"

    assert list((tmp_path / ".ge" / "control" / "contracts").glob("*.json"))
    assert list((tmp_path / ".ge" / "control" / "graphs").glob("*.json"))

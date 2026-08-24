import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_supported_python_window_is_explicit() -> None:
    project = load_pyproject()["project"]
    assert isinstance(project, dict)
    assert project["requires-python"] == ">=3.12,<3.14"
    assert project["classifiers"] == [
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ]


def test_pytest_does_not_force_a_repository_local_basetemp() -> None:
    pytest_config = load_pyproject()["tool"]["pytest"]["ini_options"]  # type: ignore[index]
    assert isinstance(pytest_config, dict)
    assert "--basetemp" not in pytest_config["addopts"]


def test_ruff_excludes_historical_acl_evidence() -> None:
    ruff_config = load_pyproject()["tool"]["ruff"]  # type: ignore[index]
    assert isinstance(ruff_config, dict)
    assert ruff_config["extend-exclude"] == [".local", ".pytest-*"]

from __future__ import annotations

import json
from pathlib import Path

from jsonschema.validators import validator_for

from graph_engineering.schema import PUBLIC_MODELS, export_schemas


def test_every_public_model_exports_valid_json_schema(tmp_path: Path) -> None:
    paths = export_schemas(tmp_path)
    assert len(paths) == len(PUBLIC_MODELS)
    for path in paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        validator_for(schema).check_schema(schema)


def test_committed_schemas_are_current(tmp_path: Path) -> None:
    generated = export_schemas(tmp_path)
    committed_dir = Path(__file__).parents[1] / "schemas"
    assert {path.name for path in generated} == {
        path.name for path in committed_dir.glob("*.schema.json")
    }
    for path in generated:
        assert path.read_text(encoding="utf-8") == (committed_dir / path.name).read_text(
            encoding="utf-8"
        )


def test_public_schema_versions_are_required() -> None:
    for name, model in PUBLIC_MODELS.items():
        schema = model.model_json_schema()
        serialized = json.dumps(schema)
        assert "schema_version" in serialized, name

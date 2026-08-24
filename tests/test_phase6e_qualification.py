from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import graph_engineering
from graph_engineering.cli import app
from graph_engineering.qualification import (
    EvidenceClassification,
    EvidenceCounts,
    EvidenceResult,
    QualificationClaim,
    QualificationEvidence,
    QualificationRepository,
    assert_secret_safe,
    collect_local_evidence,
)


def test_package_runtime_and_metadata_versions_are_one_identity() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert graph_engineering.__version__ == pyproject["project"]["version"] == "0.8.0"


def test_blocked_or_unverified_evidence_can_never_be_passed() -> None:
    for classification in (
        EvidenceClassification.BLOCKED,
        EvidenceClassification.UNVERIFIED,
    ):
        with pytest.raises(ValidationError):
            QualificationClaim(
                claim_id="claim",
                product_claim="real integration is qualified",
                required_environment="external provider",
                evidence_classification=classification,
                operation="not authorized",
                result=EvidenceResult.PASSED,
                counts=EvidenceCounts(passed=1),
                conclusion="supported",
            )


def test_passed_evidence_requires_clean_counts() -> None:
    with pytest.raises(ValidationError):
        QualificationClaim(
            claim_id="claim",
            product_claim="local smoke",
            required_environment="Windows",
            evidence_classification=EvidenceClassification.REAL_LOCAL_INTEGRATION,
            operation="ge --help",
            result=EvidenceResult.PASSED,
            counts=EvidenceCounts(passed=1, blocked=1),
            conclusion="supported",
        )


def test_passed_regression_may_disclose_separately_classified_opt_in_skips() -> None:
    claim = QualificationClaim(
        claim_id="regression",
        product_claim="deterministic regression",
        required_environment="local Windows host",
        evidence_classification=EvidenceClassification.DETERMINISTIC_FIXTURE,
        operation="python -m pytest -q",
        result=EvidenceResult.PASSED,
        counts=EvidenceCounts(collected=225, passed=221, skipped=4),
        limitation="Four real-Codex cases remain separately classified opt-in evidence.",
        conclusion="supported",
    )
    assert claim.counts.skipped == 4


def test_secret_guard_covers_key_raw_url_base64_overlap_and_cross_chunk() -> None:
    secret = "token/value+with-overlap"
    safe = {"authentication": "authenticated", "chunks": ["safe", "output"]}
    assert_secret_safe(safe, secret_values=(secret,))
    candidates = [
        {"token": "redacted"},
        {"value": secret},
        {"value": "token%2Fvalue%2Bwith-overlap"},
        {"value": "dG9rZW4vdmFsdWUrd2l0aC1vdmVybGFw"},
        {"chunks": ["token/value+with-", "overlap"]},
    ]
    for document in candidates:
        with pytest.raises(ValueError, match="secret"):
            assert_secret_safe(document, secret_values=(secret,))


def test_repository_query_is_byte_preserving_and_does_not_create_runtime_state(
    tmp_path: Path,
) -> None:
    evidence = collect_local_evidence(tmp_path, external_authorized=False)
    path = tmp_path / "qualification.json"
    repository = QualificationRepository(path)
    repository.write(evidence)
    before = path.read_bytes()
    loaded = repository.read()
    assert loaded.run_id == evidence.run_id
    assert path.read_bytes() == before
    assert not (tmp_path / ".ge").exists()


def test_default_matrix_never_substitutes_fixtures_for_external_or_platform_evidence(
    tmp_path: Path,
) -> None:
    evidence = collect_local_evidence(tmp_path, external_authorized=False)
    claims = {claim.claim_id: claim for claim in evidence.claims}
    assert claims["windows-local"].evidence_classification in {
        EvidenceClassification.REAL_LOCAL_INTEGRATION,
        EvidenceClassification.UNVERIFIED,
    }
    for claim_id in ("codex-plugin-real", "github-real", "container-real"):
        assert claims[claim_id].result in {EvidenceResult.BLOCKED, EvidenceResult.UNVERIFIED}
        assert claims[claim_id].result is not EvidenceResult.PASSED
    for claim_id in ("linux-platform", "macos-platform"):
        assert claims[claim_id].evidence_classification is EvidenceClassification.UNVERIFIED


def test_qualification_cli_collects_then_reports_without_rewriting(tmp_path: Path) -> None:
    output = tmp_path / "qualification.json"
    runner = CliRunner()
    collected = runner.invoke(app, ["qualification", "collect", "--output", str(output)])
    assert collected.exit_code == 0, collected.output
    before = output.read_bytes()
    reported = runner.invoke(app, ["qualification", "report", str(output)])
    assert reported.exit_code == 0, reported.output
    document = json.loads(reported.output)
    assert document["schema_version"] == "1.0"
    assert output.read_bytes() == before


def test_evidence_document_is_strict_and_versioned(tmp_path: Path) -> None:
    evidence = collect_local_evidence(tmp_path, external_authorized=False)
    document = evidence.model_dump(mode="json")
    document["unknown"] = True
    with pytest.raises(ValidationError):
        QualificationEvidence.model_validate(document)


def test_committed_qualification_identity_evidence_is_valid_and_append_only() -> None:
    root = Path("docs/qualification")
    paths = sorted(root.glob("phase-6e-local-identity-v*.json"))
    assert [path.stem[-2:] for path in paths] == ["v1", "v2", "v3"]
    evidence = [
        QualificationEvidence.model_validate_json(path.read_text(encoding="utf-8"))
        for path in paths
    ]
    assert len({item.run_id for item in evidence}) == 3
    assert evidence[-1].git.commit == "651352c056c5402c6a4a4057946822948a23ea66"
    codex = next(tool for tool in evidence[-1].tools if tool.name == "codex")
    assert codex.authentication.value == "authenticated"
    assert all(item.counts.passed == 0 for item in evidence)

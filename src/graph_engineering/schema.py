"""Stable JSON Schema export for every public protocol model."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .models import (
    AcceptanceCriterion,
    Artifact,
    Budget,
    BudgetUsage,
    ContractPolicy,
    ContractRef,
    ControlActionResult,
    ControlIntent,
    ControlReason,
    DeliveryPolicy,
    Edge,
    Error,
    ExecutionGraph,
    ExecutorResult,
    ExternalEffect,
    FinalReport,
    HumanControlPolicy,
    HumanMessage,
    LiveReport,
    Node,
    QueryControlIntent,
    RestartFrom,
    RouteCondition,
    RunRelationship,
    StateChangeControlIntent,
    TaskContract,
    TaskDefinition,
    UnverifiedItem,
    VerifierRequirement,
    VerifierResult,
)

PUBLIC_MODELS: dict[str, type[BaseModel]] = {
    model.__name__: model
    for model in (
        AcceptanceCriterion,
        Artifact,
        Budget,
        BudgetUsage,
        ContractPolicy,
        ContractRef,
        ControlActionResult,
        ControlIntent,
        ControlReason,
        DeliveryPolicy,
        Edge,
        Error,
        ExecutionGraph,
        ExecutorResult,
        ExternalEffect,
        FinalReport,
        HumanControlPolicy,
        HumanMessage,
        LiveReport,
        Node,
        QueryControlIntent,
        RestartFrom,
        RouteCondition,
        RunRelationship,
        StateChangeControlIntent,
        TaskContract,
        TaskDefinition,
        UnverifiedItem,
        VerifierRequirement,
        VerifierResult,
    )
}


def export_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in sorted(PUBLIC_MODELS.items()):
        path = output_dir / f"{name}.schema.json"
        document = model.model_json_schema(mode="validation")
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written

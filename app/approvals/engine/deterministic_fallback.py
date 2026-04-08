from __future__ import annotations

from datetime import datetime
from typing import Any

from app.approvals.engine.approval_engine import evaluate_approval


def build_deterministic_approval_fallback(
    *,
    project_name: str,
    project_id: str,
    category: str,
    scene: str,
    document: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    baseline = evaluate_approval(document=document, category=category, scene=scene)
    failed_items = [item for item in (baseline.get("findings") or []) if str(item.get("status") or "").strip() == "fail"]
    failed_labels = [
        str(item.get("review_content") or item.get("review_point") or "").strip()
        for item in failed_items
        if str(item.get("review_content") or item.get("review_point") or "").strip()
    ]
    pass_decision = str(baseline.get("decision") or "").strip() == "通过"
    if pass_decision:
        summary = "LLM审批暂不可用，已自动降级为规则引擎审批结果。当前规则校验通过。"
    elif failed_labels:
        summary = f"LLM审批暂不可用，已自动降级为规则引擎审批结果。当前需关注：{'、'.join(failed_labels[:6])}。"
    else:
        summary = "LLM审批暂不可用，已自动降级为规则引擎审批结果。"

    return {
        "project_name": project_name,
        "project_id": project_id,
        "category": category,
        "scene": scene,
        "document_source": document.get("document_source") or "unknown",
        "document_saved_at": document.get("document_saved_at"),
        "decision": baseline.get("decision") or "需补充材料",
        "summary": summary,
        "item_results": baseline.get("rule_results") or [],
        "risks": [] if pass_decision else failed_labels[:10],
        "missing_information": [] if pass_decision else failed_labels[:10],
        "positive_evidence": [],
        "project_commentary": "",
        "baseline": baseline,
        "segments": [],
        "run_dir": "",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "decision_source": "deterministic_fallback",
        "fallback_reason": reason,
    }

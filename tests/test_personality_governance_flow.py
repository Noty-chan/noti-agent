import json
import sqlite3
from pathlib import Path

from noty.memory.sqlite_db import SQLiteDBManager
from noty.prompts.governance import ApprovalDecision, PersonalityProposal
from noty.prompts.prompt_builder import ModularPromptBuilder
from noty.tools.tool_executor import SafeToolExecutor


def _change_personality(text: str) -> str:
    return f"applied:{text}"


def test_personality_governance_e2e(tmp_path: Path):
    db_path = tmp_path / "noty.db"
    prompts_dir = tmp_path / "prompts"
    actions_dir = tmp_path / "actions"

    db = SQLiteDBManager(str(db_path))
    proposal_id = db.create_personality_proposal(author="owner", diff_summary="Сделать тон резче", risk="high")
    db.review_personality_proposal(proposal_id=proposal_id, decision="approve", reviewer="lead-owner")

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT author, diff_summary, risk, decision, reviewer FROM personality_change_proposals WHERE id=?",
        (proposal_id,),
    ).fetchone()
    conn.close()
    assert row == ("owner", "Сделать тон резче", "high", "approve", "lead-owner")

    executor = SafeToolExecutor(owner_id=100, actions_log_dir=str(actions_dir))
    executor.register_personality_tool("update_personality", _change_personality)

    denied = executor.execute(
        {"name": "update_personality", "arguments": {"text": "x"}},
        user_id=999,
        chat_id=1,
        is_private=True,
    )
    assert denied["status"] == "error"

    waiting = executor.execute(
        {"name": "update_personality", "arguments": {"text": "v2"}},
        user_id=100,
        chat_id=1,
        is_private=True,
    )
    assert waiting["status"] == "awaiting_confirmation"
    confirmed = executor.confirm_pending(waiting["confirmation_id"])
    assert confirmed["status"] == "success"

    builder = ModularPromptBuilder(str(prompts_dir))
    proposal = PersonalityProposal(
        proposal_id=f"pr-{proposal_id}",
        author="owner",
        diff_summary="Сделать тон резче",
        risk="high",
        new_personality_text="Новый personality слой",
    )
    preview = builder.dry_run_preview(proposal, context={"messages": [{"role": "user", "content": "тест"}]})
    assert preview["status"] == "dry_run"
    assert "dry-run" in preview["preview_prompt"]

    decision = ApprovalDecision(
        proposal_id=proposal.proposal_id,
        reviewer="lead-owner",
        decision="approve",
        reason="manual approval",
    )
    result = builder.approve_with_kpi_guardrails(
        proposal=proposal,
        decision=decision,
        baseline_kpi={"response_quality": 0.9},
        candidate_kpi={"response_quality": 0.6},
        degradation_threshold=0.1,
    )
    assert result["status"] == "rolled_back"
    assert result["rollback_event"]["trigger"] == "kpi_degradation"

    audit_path = actions_dir / "dangerous_audit.jsonl"
    lines = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    stages = {line["stage"] for line in lines}
    assert "access_denied" in stages
    assert "confirmation_requested" in stages
    assert "confirmed_and_executed" in stages

"""Supabase database operations for guidelines and reviews."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_KEY
from models.guideline import ParsedGuideline
from models.review_result import ReviewReport


def _get_client() -> Client:
    """Get Supabase client (cached via module-level)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Guidelines ──────────────────────────────────────────


def save_guideline(campaign_name: str, guideline: ParsedGuideline) -> int:
    """Save a parsed guideline to Supabase. Returns the row ID."""
    sb = _get_client()
    data = {
        "campaign_name": campaign_name,
        "guideline_json": guideline.model_dump(),
    }
    # Check if campaign already exists → update
    existing = (
        sb.table("vc_guidelines")
        .select("id")
        .eq("campaign_name", campaign_name)
        .execute()
    )
    if existing.data:
        row_id = existing.data[0]["id"]
        sb.table("vc_guidelines").update({
            "guideline_json": guideline.model_dump(),
            "updated_at": datetime.now().isoformat(),
        }).eq("id", row_id).execute()
        return row_id
    else:
        result = sb.table("vc_guidelines").insert(data).execute()
        return result.data[0]["id"]


def list_guidelines() -> list[dict]:
    """Return list of saved guidelines: [{id, campaign_name, created_at}, ...]."""
    sb = _get_client()
    result = (
        sb.table("vc_guidelines")
        .select("id, campaign_name, created_at, updated_at")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def load_guideline(guideline_id: int) -> tuple[str, ParsedGuideline]:
    """Load a guideline by ID. Returns (campaign_name, ParsedGuideline)."""
    sb = _get_client()
    result = (
        sb.table("vc_guidelines")
        .select("campaign_name, guideline_json")
        .eq("id", guideline_id)
        .single()
        .execute()
    )
    row = result.data
    guideline = ParsedGuideline.model_validate(row["guideline_json"])
    return row["campaign_name"], guideline


def load_guideline_by_name(campaign_name: str) -> Optional[tuple[int, ParsedGuideline]]:
    """Load a guideline by campaign name. Returns (id, ParsedGuideline) or None."""
    sb = _get_client()
    result = (
        sb.table("vc_guidelines")
        .select("id, guideline_json")
        .eq("campaign_name", campaign_name)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    guideline = ParsedGuideline.model_validate(row["guideline_json"])
    return row["id"], guideline


def delete_guideline(guideline_id: int) -> None:
    """Delete a guideline by ID."""
    sb = _get_client()
    sb.table("vc_guidelines").delete().eq("id", guideline_id).execute()


# ── Reviews ─────────────────────────────────────────────


def save_review(
    campaign_name: str,
    creator_name: str,
    report: ReviewReport,
    round_num: int = 1,
    campaign_id: Optional[int] = None,
) -> int:
    """Save a review result. Auto-approves if score >= 90 and no manual flags. Returns the row ID."""
    sb = _get_client()
    data = {
        "campaign_name": campaign_name,
        "creator_name": creator_name,
        "round": round_num,
        "overall_score": report.overall_score,
        "overall_status": report.overall_status,
        "report_json": report.model_dump(),
    }
    if campaign_id:
        data["campaign_id"] = campaign_id
    # 90+ with no manual flags → auto-approve
    if report.overall_score >= 90 and not report.manual_review_flags:
        data["admin_decision"] = "auto_approved"
    result = sb.table("vc_reviews").insert(data).execute()
    return result.data[0]["id"]


def get_previous_review(
    campaign_name: str, creator_name: str
) -> Optional[tuple[ReviewReport, int]]:
    """Get the most recent review for a creator in a campaign.

    Returns (report, round_number) or None.
    """
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("report_json, round")
        .eq("campaign_name", campaign_name)
        .eq("creator_name", creator_name)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    report = ReviewReport.model_validate(row["report_json"])
    return report, row["round"]


def get_next_round(campaign_name: str, creator_name: str) -> int:
    """Get the next round number for a creator."""
    prev = get_previous_review(campaign_name, creator_name)
    if prev is None:
        return 1
    return prev[1] + 1


def list_reviews(campaign_name: str) -> list[dict]:
    """List all reviews for a campaign."""
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("id, creator_name, round, overall_score, overall_status, created_at, admin_decision, admin_memo, brand_feedback")
        .eq("campaign_name", campaign_name)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def get_submission_status(campaign_name: str) -> list[dict]:
    """Get latest submission per creator for a campaign.

    Returns list of {creator_name, round, overall_score, overall_status, created_at, ...}.
    """
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("id, creator_name, round, overall_score, overall_status, created_at, admin_decision, brand_feedback, caption_check_result")
        .eq("campaign_name", campaign_name)
        .order("created_at", desc=True)
        .execute()
    )
    # Deduplicate: keep only latest per creator
    seen: set[str] = set()
    unique = []
    for row in result.data:
        if row["creator_name"] not in seen:
            seen.add(row["creator_name"])
            unique.append(row)
    return unique


def get_creator_reviews(campaign_name: str, creator_name: str) -> list[dict]:
    """Get all reviews for a specific creator in a campaign, newest first.

    Returns list of {id, round, overall_score, overall_status, created_at, report_json, ...}.
    """
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("id, round, overall_score, overall_status, created_at, report_json, admin_decision, admin_memo, brand_feedback, caption_check_result")
        .eq("campaign_name", campaign_name)
        .eq("creator_name", creator_name)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def load_review(review_id: int) -> Optional[ReviewReport]:
    """Load a full review report by ID."""
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("report_json")
        .eq("id", review_id)
        .single()
        .execute()
    )
    if not result.data:
        return None
    return ReviewReport.model_validate(result.data["report_json"])


# ── Admin Decision & Brand Feedback (vc_reviews 컬럼) ──


def save_admin_decision(review_id: int, decision: str, memo: str = "") -> None:
    """Save admin manual decision on a review (updates vc_reviews row).

    decision: 'approved', 'rejected', or 'revision_needed'
    Columns: admin_decision, admin_memo
    """
    sb = _get_client()
    sb.table("vc_reviews").update({
        "admin_decision": decision,
        "admin_memo": memo,
    }).eq("id", review_id).execute()


def save_brand_feedback(review_id: int, feedback: str, set_revision: bool = True) -> None:
    """Save brand feedback on a review (updates vc_reviews row).

    Also sets admin_decision to 'revision_needed' so the creator sees they need to revise.
    Column: brand_feedback
    """
    sb = _get_client()
    update_data: dict = {"brand_feedback": feedback}
    if set_revision:
        update_data["admin_decision"] = "revision_needed"
    sb.table("vc_reviews").update(update_data).eq("id", review_id).execute()


def get_latest_brand_feedback(campaign_name: str, creator_name: str) -> Optional[str]:
    """Get the most recent brand feedback for a creator in a campaign.

    Searches all reviews (not just latest) for one that has brand_feedback set.
    Returns the feedback text or None.
    """
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("brand_feedback")
        .eq("campaign_name", campaign_name)
        .eq("creator_name", creator_name)
        .neq("brand_feedback", "null")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data and result.data[0].get("brand_feedback"):
        return result.data[0]["brand_feedback"]
    return None


def save_caption_check(review_id: int, result: dict) -> None:
    """Save caption check result on a review (updates vc_reviews row).

    Column: caption_check_result (jsonb)
    """
    sb = _get_client()
    sb.table("vc_reviews").update({
        "caption_check_result": result,
    }).eq("id", review_id).execute()


def get_campaigns_summary() -> list[dict]:
    """Get summary stats for all campaigns.

    Returns list of {campaign_name, total_creators, avg_score, approved, revision_needed, rejected}.
    """
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("campaign_name, creator_name, overall_score, overall_status, admin_decision, caption_check_result, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    # Aggregate per campaign (latest per creator only)
    from collections import defaultdict
    campaigns: dict[str, dict] = {}
    seen: dict[str, set] = defaultdict(set)

    for row in result.data:
        cn = row["campaign_name"]
        cr = row["creator_name"]
        if cr in seen[cn]:
            continue
        seen[cn].add(cr)
        if cn not in campaigns:
            campaigns[cn] = {
                "campaign_name": cn,
                "total_creators": 0,
                "scores": [],
                "approved": 0,
                "revision_needed": 0,
                "rejected": 0,
                "caption_done": 0,
            }
        c = campaigns[cn]
        c["total_creators"] += 1
        c["scores"].append(row["overall_score"] or 0)
        ad = row.get("admin_decision") or row.get("overall_status") or ""
        if ad in ("approved", "auto_approved"):
            c["approved"] += 1
        elif ad == "revision_needed":
            c["revision_needed"] += 1
        elif ad == "rejected":
            c["rejected"] += 1
        if row.get("caption_check_result"):
            c["caption_done"] += 1

    summaries = []
    for c in campaigns.values():
        c["avg_score"] = round(sum(c["scores"]) / len(c["scores"])) if c["scores"] else 0
        del c["scores"]
        summaries.append(c)
    return summaries

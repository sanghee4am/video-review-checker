"""Supabase database operations for guidelines and reviews."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from functools import lru_cache
from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_KEY
from models.guideline import ParsedGuideline
from models.review_result import ReviewReport


@lru_cache(maxsize=1)
def _get_client() -> Client:
    """Get Supabase client (cached — single instance reused across reruns)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Guidelines (guidelines 테이블의 gl_parsed_json 사용) ──


def save_guideline(gl_id: str, guideline: ParsedGuideline) -> str:
    """Save a parsed guideline to guidelines.gl_parsed_json. Returns the gl_id."""
    sb = _get_client()
    sb.table("guidelines").update({
        "gl_parsed_json": guideline.model_dump(),
        "updated_at": datetime.now().isoformat(),
    }).eq("id", gl_id).execute()
    return gl_id


def list_guidelines() -> list[dict]:
    """Return list of guidelines that have parsed JSON.

    Joins through campaigns to provide campaign_name for display.
    """
    sb = _get_client()
    result = (
        sb.table("guidelines")
        .select("id, gl_campaign_id, gl_header_text, gl_parsed_json, created_at, updated_at, campaigns(cam_brand_name, cam_product_name)")
        .not_.is_("gl_parsed_json", "null")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    # Add campaign_name for backward compatibility
    for row in result.data:
        cam = row.get("campaigns") or {}
        row["campaign_name"] = " ".join(filter(None, [cam.get("cam_brand_name"), cam.get("cam_product_name")])) or row.get("gl_header_text") or "Unknown"
    return result.data


def load_guideline(gl_id: str) -> Optional[ParsedGuideline]:
    """Load a parsed guideline by gl_id. Returns ParsedGuideline or None."""
    sb = _get_client()
    result = (
        sb.table("guidelines")
        .select("gl_parsed_json")
        .eq("id", gl_id)
        .single()
        .execute()
    )
    if not result.data or not result.data.get("gl_parsed_json"):
        return None
    return ParsedGuideline.model_validate(result.data["gl_parsed_json"])


def get_guideline_source_url(gl_id: str) -> Optional[str]:
    """Return guidelines.gl_source_url for a given gl_id, or None if absent.

    Used by review-by-path to fall back to an external guideline tool
    (campaign-guideline-tool) when gl_parsed_json has never been populated.
    """
    sb = _get_client()
    result = (
        sb.table("guidelines")
        .select("gl_source_url")
        .eq("id", gl_id)
        .single()
        .execute()
    )
    if not result.data:
        return None
    url = result.data.get("gl_source_url")
    return url if isinstance(url, str) and url else None


def delete_guideline_parsed(gl_id: str) -> None:
    """Clear gl_parsed_json for a guideline (does not delete the guidelines row)."""
    sb = _get_client()
    sb.table("guidelines").update({
        "gl_parsed_json": None,
    }).eq("id", gl_id).execute()


# ── Reviews ─────────────────────────────────────────────


def save_review(
    campaign_name: str,
    creator_name: str,
    report: ReviewReport,
    round_num: int = 1,
    gl_id: Optional[str] = None,
    ci_id: Optional[str] = None,
    video_url: Optional[str] = None,
) -> int:
    """Save a review result. Auto-approves if score >= 90 and no manual flags. Returns the row ID.

    If a placeholder row exists for the same (ci_id, round) — created by
    Workers at draft submission time — fill that row instead of inserting a
    duplicate. This keeps one vc_reviews row per (ci_id, round).
    """
    sb = _get_client()
    data = {
        "campaign_name": campaign_name,
        "creator_name": creator_name,
        "round": round_num,
        "overall_score": report.overall_score,
        "overall_status": report.overall_status,
        "report_json": report.model_dump(),
    }
    if gl_id:
        data["gl_id"] = gl_id
    if ci_id:
        data["ci_id"] = ci_id
    if video_url:
        data["video_url"] = video_url
    # 90+ with no manual flags → auto-approve
    if report.overall_score >= 90 and not report.manual_review_flags:
        data["admin_decision"] = "auto_approved"
    # < 80 → auto-reject (creator must fix before brand sees)
    elif report.overall_score < 80:
        data["admin_decision"] = "revision_needed"

    # Try to fill an existing placeholder for this draft.
    # Workers' POST /draft inserts the placeholder without ci_id (it has gl_id
    # + creator_name + round only), so the match is (gl_id, creator_name, round).
    # ci_id is preferred when available but falls back to gl_id+name+round.
    placeholder_id: Optional[int] = None
    if ci_id:
        existing = (
            sb.table("vc_reviews")
            .select("id")
            .eq("ci_id", ci_id)
            .eq("round", round_num)
            .is_("overall_score", "null")
            .order("created_at", desc=False)
            .limit(1)
            .execute()
        )
        if existing.data:
            placeholder_id = existing.data[0]["id"]
    if placeholder_id is None and gl_id:
        existing = (
            sb.table("vc_reviews")
            .select("id")
            .eq("gl_id", gl_id)
            .eq("creator_name", creator_name)
            .eq("round", round_num)
            .is_("overall_score", "null")
            .order("created_at", desc=False)
            .limit(1)
            .execute()
        )
        if existing.data:
            placeholder_id = existing.data[0]["id"]

    if placeholder_id is not None:
        sb.table("vc_reviews").update(data).eq("id", placeholder_id).execute()
        return placeholder_id

    result = sb.table("vc_reviews").insert(data).execute()
    return result.data[0]["id"]


_ROUND_TO_DRAFT_STATUS = {
    1: "1st_draft_submitted",
    2: "2nd_draft_submitted",
    3: "3rd_draft_submitted",
    4: "4th_draft_submitted",
}


def update_ci_status_after_review(ci_id: str, score: int, round_num: int):
    """검수 점수에 따라 campaign_influencers 상태 업데이트.
    80점+ → {N}st_draft_submitted (해당 차수)
    80점- → 현재 상태 유지 (Workers 가 이미 설정한 상태 그대로 둔다)

    round_num 은 검수 자체의 차수 (review-by-path 에서 계산된 review_round).
    예전 구현은 `is_first = not bool(ci_1st_draft_urls)` 로 추론했으나, Workers 가
    AI 검수 트리거 전에 이미 ci_*_draft_urls 를 채워둔 상태라 항상 `is_first=False` 가
    되어 1차 제출인 인플이 '2nd_draft_submitted' 로 잘못 옮겨가는 버그가 있었음.
    """
    sb = _get_client()
    if score < 80:
        return
    status = _ROUND_TO_DRAFT_STATUS.get(round_num)
    if not status:
        return
    sb.table("campaign_influencers").update(
        {"ci_status": status, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", ci_id).execute()


def get_ci_info(ci_id: str) -> Optional[dict]:
    """campaign_influencers에서 검수에 필요한 정보 조회."""
    sb = _get_client()
    result = sb.table("campaign_influencers").select(
        "id, ci_username, ci_guideline_id, ci_campaign_id, ci_status, "
        "ci_1st_draft_urls, ci_2nd_draft_urls, "
        "campaigns(cam_name)"
    ).eq("id", ci_id).single().execute()
    return result.data if result.data else None


def download_from_storage(path: str) -> bytes:
    """Supabase Storage에서 파일 다운로드 (signed URL 방식)."""
    import httpx
    sb = _get_client()
    signed = sb.storage.from_("drafts").create_signed_url(path, 300)
    url = signed.get("signedURL") or signed.get("signedUrl")
    if not url:
        raise RuntimeError(f"Failed to create signed URL for {path}: {signed}")
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    return resp.content


def get_previous_review(
    campaign_name: str, creator_name: str
) -> Optional[tuple[ReviewReport, int]]:
    """Get the most recent COMPLETED review for a creator in a campaign.

    Placeholder rows inserted by Workers (overall_score IS NULL) are skipped —
    otherwise the next real review would bump round number off-by-one
    (placeholder round=1 + new review → round 2, on a creator who only
    submitted a 1st draft).

    Returns (report, round_number) or None.
    """
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("report_json, round")
        .eq("campaign_name", campaign_name)
        .eq("creator_name", creator_name)
        .not_.is_("overall_score", "null")
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


def list_reviews(campaign_name: str, limit: int = 200) -> list[dict]:
    """List reviews for a campaign (newest first, default 200)."""
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("id, creator_name, round, overall_score, overall_status, created_at, admin_decision, admin_memo, brand_feedback, report_json, video_url")
        .eq("campaign_name", campaign_name)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def get_submission_status(campaign_name: str, limit: int = 500) -> list[dict]:
    """Get latest submission per creator for a campaign.

    Returns list of {creator_name, round, overall_score, overall_status, created_at, ...}.
    """
    sb = _get_client()
    result = (
        sb.table("vc_reviews")
        .select("id, creator_name, round, overall_score, overall_status, created_at, admin_decision, brand_feedback, caption_check_result")
        .eq("campaign_name", campaign_name)
        .order("created_at", desc=True)
        .limit(limit)
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
        .limit(1000)
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


# ── Content Checks (무가 콘텐츠 검수) ──────────────────────


def create_content_check(
    campaign_name: str,
    creator_name: str,
    url: str,
    caption: str = "",
    post_type: str = "",
    ci_id: Optional[str] = None,
    gl_id: Optional[str] = None,
) -> int:
    """Create a pending content check job. Returns the row ID."""
    sb = _get_client()
    data: dict = {
        "campaign_name": campaign_name,
        "creator_name": creator_name,
        "url": url,
        "caption": caption,
        "post_type": post_type,
        "status": "pending",
    }
    if ci_id:
        data["ci_id"] = ci_id
    if gl_id:
        data["gl_id"] = gl_id
    result = sb.table("vc_content_checks").insert(data).execute()
    return result.data[0]["id"]


def get_pending_content_checks(limit: int = 10) -> list[dict]:
    """Get pending content check jobs for the worker to process."""
    sb = _get_client()
    result = (
        sb.table("vc_content_checks")
        .select("*")
        .eq("status", "pending")
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return result.data


def update_content_check(check_id: int, status: str, result_json: Optional[dict] = None, error: Optional[str] = None) -> None:
    """Update a content check job status and result."""
    sb = _get_client()
    data: dict = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    if result_json is not None:
        data["result_json"] = result_json
    if error is not None:
        data["error"] = error
    sb.table("vc_content_checks").update(data).eq("id", check_id).execute()


def get_content_check(check_id: int) -> Optional[dict]:
    """Get a content check by ID."""
    sb = _get_client()
    result = sb.table("vc_content_checks").select("*").eq("id", check_id).limit(1).execute()
    return result.data[0] if result.data else None

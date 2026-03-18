from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.review_result import ReviewReport

REVIEW_HISTORY_DIR = Path(__file__).parent.parent / "review_history"
REVIEW_HISTORY_DIR.mkdir(exist_ok=True)


def _campaign_key(campaign_name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in campaign_name).strip()


def save_review(campaign_name: str, creator_name: str, report: ReviewReport, round_num: int = 1) -> Path:
    """Save a review result to history."""
    key = _campaign_key(campaign_name)
    campaign_dir = REVIEW_HISTORY_DIR / key
    campaign_dir.mkdir(exist_ok=True)

    safe_creator = _campaign_key(creator_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_creator}_round{round_num}_{timestamp}.json"

    data = {
        "campaign_name": campaign_name,
        "creator_name": creator_name,
        "round": round_num,
        "timestamp": datetime.now().isoformat(),
        "report": report.model_dump(),
    }

    filepath = campaign_dir / filename
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def get_previous_review(campaign_name: str, creator_name: str) -> Optional[tuple[ReviewReport, int]]:
    """Get the most recent previous review for a creator in a campaign.

    Returns (report, round_number) or None.
    """
    key = _campaign_key(campaign_name)
    campaign_dir = REVIEW_HISTORY_DIR / key
    if not campaign_dir.exists():
        return None

    safe_creator = _campaign_key(creator_name)
    files = sorted(
        [f for f in campaign_dir.glob(f"{safe_creator}_round*.json")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not files:
        return None

    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
        report = ReviewReport.model_validate(data["report"])
        round_num = data.get("round", 1)
        return report, round_num
    except Exception:
        return None


def get_next_round(campaign_name: str, creator_name: str) -> int:
    """Get the next round number for a creator."""
    prev = get_previous_review(campaign_name, creator_name)
    if prev is None:
        return 1
    return prev[1] + 1


def list_review_history(campaign_name: str) -> list[dict]:
    """List all reviews for a campaign."""
    key = _campaign_key(campaign_name)
    campaign_dir = REVIEW_HISTORY_DIR / key
    if not campaign_dir.exists():
        return []

    results = []
    for f in sorted(campaign_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append({
                "creator_name": data.get("creator_name", ""),
                "round": data.get("round", 1),
                "timestamp": data.get("timestamp", ""),
                "score": data.get("report", {}).get("overall_score", 0),
                "status": data.get("report", {}).get("overall_status", ""),
                "filepath": f,
            })
        except Exception:
            pass
    return results

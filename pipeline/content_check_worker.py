"""Content check worker — polls Supabase for pending unpaid content checks.

Usage:
    python -m pipeline.content_check_worker          # 1회 실행
    python -m pipeline.content_check_worker --loop    # 30초 간격 반복
"""
from __future__ import annotations

import sys
import os
import time
import traceback

# video-review-checker 루트를 Python 경로에 추가
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db import (
    get_pending_content_checks,
    update_content_check,
    load_guideline_by_name,
)
from analyzer.unpaid_checker import (
    download_video_from_url,
    process_video_light,
    run_unpaid_check,
)
from analyzer.upload_checker import check_upload, fetch_post_content


def process_one(job: dict) -> None:
    """Process a single content check job."""
    check_id = job["id"]
    url = job["url"]
    campaign_name = job["campaign_name"]
    caption = job.get("caption") or ""
    post_type = job.get("post_type") or ""

    print(f"[{check_id}] Processing: {campaign_name} — {url[:60]}")
    update_content_check(check_id, "processing")

    checks: list[dict] = []

    # 1. Video format (from client-side oEmbed data)
    if post_type:
        is_photo = post_type.lower() == "photo"
        checks.append({
            "name": "Video Format",
            "passed": not is_photo,
            "message": "Photo slideshow detected — video required" if is_photo else "Video format confirmed",
        })
    else:
        checks.append({
            "name": "Video Format",
            "passed": True,
            "message": "Could not verify format — skipped",
        })

    # 2 & 3. Video analysis (download + frames + AI)
    try:
        # Load guideline for product info
        gl_result = load_guideline_by_name(campaign_name)
        product_name = campaign_name
        concept = ""
        if gl_result:
            _gid, guideline = gl_result
            product_name = guideline.product_name or campaign_name
            concept = guideline.concept or guideline.content_objective or ""

        # Download video
        print(f"  Downloading video...")
        video_bytes, filename = download_video_from_url(url)
        print(f"  Downloaded: {len(video_bytes) / 1024 / 1024:.1f}MB")

        # Extract frames (light — 3s intervals)
        print(f"  Extracting frames...")
        processed = process_video_light(video_bytes, filename)
        print(f"  Extracted {len(processed.frames)} frames from {processed.duration:.1f}s video")

        # AI analysis
        print(f"  Running AI analysis...")
        result = run_unpaid_check(
            video=processed,
            product_name=product_name,
            concept=concept,
            caption=caption,
        )

        checks.append({
            "name": "Not Multi-Product",
            "passed": not result.get("is_multi_product", False),
            "message": result.get("multi_product_detail", ""),
        })
        checks.append({
            "name": "Not Simple Unboxing",
            "passed": not result.get("is_simple_unboxing", False),
            "message": result.get("unboxing_detail", ""),
        })
        print(f"  AI done: multi_product={result.get('is_multi_product')}, unboxing={result.get('is_simple_unboxing')}")

    except Exception as e:
        print(f"  Video analysis error: {e}")
        checks.append({
            "name": "Not Multi-Product",
            "passed": True,
            "message": f"Video analysis error: {str(e)[:200]}",
        })
        checks.append({
            "name": "Not Simple Unboxing",
            "passed": True,
            "message": f"Video analysis error: {str(e)[:200]}",
        })

    # 4. Caption elements check
    if caption and gl_result:
        try:
            cap_result = check_upload(caption, guideline)
            for item in cap_result.get("checks", []):
                checks.append({
                    "name": item["element"],
                    "passed": item["status"] == "found",
                    "message": "Found in caption" if item["status"] == "found" else "Missing from caption",
                })
        except Exception as e:
            print(f"  Caption check error: {e}")

    all_passed = all(c["passed"] for c in checks)

    update_content_check(check_id, "completed", result_json={
        "passed": all_passed,
        "checks": checks,
    })
    print(f"  ✓ Done: {'PASS' if all_passed else 'FAIL'}")


def run_once(max_workers: int = 3) -> int:
    """Process all pending jobs in parallel. Returns number processed."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    jobs = get_pending_content_checks(limit=10)
    if not jobs:
        print("No pending content checks.")
        return 0

    print(f"Found {len(jobs)} pending content check(s) (parallel={max_workers})")
    processed = 0

    def _safe_process(job):
        try:
            process_one(job)
            return True
        except Exception as e:
            print(f"[{job['id']}] Fatal error: {e}")
            traceback.print_exc()
            update_content_check(job["id"], "failed", error=str(e)[:500])
            return False

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_safe_process, job): job for job in jobs}
        for future in as_completed(futures):
            if future.result():
                processed += 1
    return processed


def run_loop(interval: int = 30) -> None:
    """Poll continuously with given interval (seconds)."""
    print(f"Content check worker started (polling every {interval}s)")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"Loop error: {e}")
            traceback.print_exc()
        time.sleep(interval)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        run_loop()
    else:
        run_once()

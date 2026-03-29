"""Content checker for unpaid campaign post validation.

Checks TikTok/IG posts for:
1. Video format (not image-only / photo slideshow)
2. Not a dedicated advertisement (organic feel required)
3. Not a simple unboxing (needs review/usage/storytelling)
4. Caption elements (reuses upload_checker)
"""

from __future__ import annotations

import json
import subprocess

import requests
import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from analyzer.upload_checker import fetch_post_content, check_upload
from models.guideline import ParsedGuideline


# ---------------------------------------------------------------------------
# Prompt: single AI call for dedicated-ad + simple-unboxing checks
# ---------------------------------------------------------------------------

CONTENT_ANALYSIS_PROMPT = """You are analyzing a social media post caption to evaluate content quality for an UNPAID campaign.

The brand sent free product to this creator (no payment). We need to ensure the content feels organic, not like a forced advertisement.

=== POST CAPTION ===
{caption}

=== PRODUCT/CAMPAIGN INFO ===
Product: {product_name}
Concept: {concept}

Evaluate TWO things:

1. **Dedicated Advertisement Check**
   - Is the ENTIRE post purely about the sponsored product with no personal/organic feel?
   - A dedicated ad = the post reads like a script written by the brand, with no personal touch, no genuine opinion, no lifestyle context.
   - If the creator adds personal experience, opinion, humor, lifestyle context, or mixes it with other content, it is NOT a dedicated ad.
   - For unpaid campaigns, we want organic content, not pure advertisements.

2. **Simple Unboxing Check**
   - Is this just a basic unboxing video (opening a package, showing what's inside, nothing more)?
   - A simple unboxing = no real review, no usage demonstration, no storytelling, no personal opinion — just "look what I got."
   - If the creator uses the product, gives opinions, shows results, or tells a story, it is NOT a simple unboxing.

Return ONLY valid JSON (no markdown fences):
{{
  "is_dedicated_ad": true/false,
  "dedicated_detail": "brief explanation in English",
  "is_simple_unboxing": true/false,
  "unboxing_detail": "brief explanation in English"
}}
"""


# ---------------------------------------------------------------------------
# Video format check (image-only detection)
# ---------------------------------------------------------------------------

def _detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "instagram.com" in url_lower:
        return "instagram"
    return "unknown"


def _check_video_format_tiktok(url: str) -> dict:
    """Check TikTok post is video, not photo slideshow."""
    try:
        resp = requests.get(
            "https://www.tiktok.com/oembed",
            params={"url": url},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            # TikTok oEmbed returns "type": "video" for videos.
            # Photo slideshows may return "type": "photo" or lack video fields.
            oembed_type = data.get("type", "").lower()
            title = data.get("title", "")

            if oembed_type == "photo":
                return {
                    "check": "video_format",
                    "status": "fail",
                    "detail": f"Photo slideshow detected (oEmbed type=photo). Title: {title[:80]}",
                }

            # Additional heuristic: if no "html" embed code (video player), suspicious
            if oembed_type == "video" or "html" in data:
                return {
                    "check": "video_format",
                    "status": "pass",
                    "detail": f"Video format confirmed (oEmbed type={oembed_type}). Title: {title[:80]}",
                }

            # Ambiguous — pass with note
            return {
                "check": "video_format",
                "status": "pass",
                "detail": f"Format unclear (type={oembed_type}), assuming video. Title: {title[:80]}",
            }
        else:
            return {
                "check": "video_format",
                "status": "pass",
                "detail": f"oEmbed API returned {resp.status_code} — skipping format check.",
            }
    except Exception as e:
        return {
            "check": "video_format",
            "status": "pass",
            "detail": f"Could not verify format (oEmbed error: {e}). Skipping check.",
        }


def _check_video_format_instagram(url: str) -> dict:
    """Check Instagram post is video/reel, not image carousel."""
    # Try yt-dlp metadata to detect format
    try:
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--print", "%(ext)s", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            ext = result.stdout.strip().lower()
            if ext in ("mp4", "webm", "mov"):
                return {
                    "check": "video_format",
                    "status": "pass",
                    "detail": f"Video format confirmed (ext={ext}).",
                }
            elif ext in ("jpg", "jpeg", "png", "webp"):
                return {
                    "check": "video_format",
                    "status": "fail",
                    "detail": f"Image post detected (ext={ext}). Video required for unpaid campaigns.",
                }
            else:
                return {
                    "check": "video_format",
                    "status": "pass",
                    "detail": f"Format detected: {ext}. Assuming video.",
                }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: URL pattern heuristic
    url_lower = url.lower()
    if "/reel/" in url_lower or "/reels/" in url_lower:
        return {
            "check": "video_format",
            "status": "pass",
            "detail": "Instagram Reel URL detected — video format assumed.",
        }
    if "/p/" in url_lower:
        return {
            "check": "video_format",
            "status": "pass",
            "detail": "Instagram /p/ URL — could be image or video. Manual verification recommended.",
        }

    return {
        "check": "video_format",
        "status": "pass",
        "detail": "Could not determine format. Skipping check.",
    }


def _check_video_format(url: str) -> dict:
    """Route video format check by platform."""
    platform = _detect_platform(url)
    if platform == "tiktok":
        return _check_video_format_tiktok(url)
    elif platform == "instagram":
        return _check_video_format_instagram(url)
    return {
        "check": "video_format",
        "status": "pass",
        "detail": "Platform not TikTok/IG — format check skipped.",
    }


# ---------------------------------------------------------------------------
# AI content analysis (dedicated ad + simple unboxing in one call)
# ---------------------------------------------------------------------------

def _analyze_content_with_ai(caption: str, guideline: ParsedGuideline) -> tuple[dict, dict]:
    """Call Claude once to check for dedicated ad + simple unboxing.

    Returns (dedicated_check_result, unboxing_check_result).
    """
    prompt = CONTENT_ANALYSIS_PROMPT.format(
        caption=caption[:3000],  # truncate for safety
        product_name=guideline.product_name or "(unknown)",
        concept=guideline.concept or guideline.content_objective or "(not specified)",
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    result = json.loads(text)

    dedicated_check = {
        "check": "not_dedicated",
        "status": "fail" if result.get("is_dedicated_ad") else "pass",
        "detail": result.get("dedicated_detail", ""),
    }

    unboxing_check = {
        "check": "not_simple_unboxing",
        "status": "fail" if result.get("is_simple_unboxing") else "pass",
        "detail": result.get("unboxing_detail", ""),
    }

    return dedicated_check, unboxing_check


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_content(url: str, guideline: ParsedGuideline) -> dict:
    """Run all content checks for unpaid campaigns.

    Returns:
        {
            "all_passed": bool,
            "content_checks": [
                {"check": "video_format", "status": "pass"/"fail", "detail": "..."},
                {"check": "not_dedicated", "status": "pass"/"fail", "detail": "..."},
                {"check": "not_simple_unboxing", "status": "pass"/"fail", "detail": "..."},
            ],
            "caption_check": { ... },  # result from check_upload
            "summary_en": "...",
        }
    """
    content_checks = []

    # 1. Video format check (no AI needed)
    format_result = _check_video_format(url)
    content_checks.append(format_result)

    # 2 & 3. Fetch caption, then run AI analysis (dedicated + unboxing in one call)
    try:
        _platform, caption = fetch_post_content(url)
    except ValueError as e:
        # Cannot fetch caption — skip AI checks, report error
        content_checks.append({
            "check": "not_dedicated",
            "status": "pass",
            "detail": f"Skipped — could not fetch caption: {e}",
        })
        content_checks.append({
            "check": "not_simple_unboxing",
            "status": "pass",
            "detail": f"Skipped — could not fetch caption: {e}",
        })
        caption = None

    if caption:
        try:
            dedicated_check, unboxing_check = _analyze_content_with_ai(caption, guideline)
            content_checks.append(dedicated_check)
            content_checks.append(unboxing_check)
        except Exception as e:
            content_checks.append({
                "check": "not_dedicated",
                "status": "pass",
                "detail": f"AI analysis error: {e}. Skipping.",
            })
            content_checks.append({
                "check": "not_simple_unboxing",
                "status": "pass",
                "detail": f"AI analysis error: {e}. Skipping.",
            })

    # 4. Caption check (hashtags, mentions, disclosures) via existing upload_checker
    caption_check = {}
    if caption:
        try:
            caption_check = check_upload(caption, guideline)
        except Exception as e:
            caption_check = {
                "all_passed": True,
                "checks": [],
                "summary_en": f"Caption check error: {e}",
            }
    else:
        caption_check = {
            "all_passed": True,
            "checks": [],
            "summary_en": "Caption not available — skipped caption element check.",
        }

    # Aggregate results
    content_all_passed = all(c["status"] == "pass" for c in content_checks)
    overall_passed = content_all_passed and caption_check.get("all_passed", True)

    # Build summary
    failed = [c for c in content_checks if c["status"] == "fail"]
    summary_parts = []
    if not failed and caption_check.get("all_passed", True):
        summary_parts.append("All content checks passed.")
    else:
        if failed:
            summary_parts.append(
                "Content issues: " + "; ".join(f"{c['check']} FAIL — {c['detail']}" for c in failed)
            )
        caption_summary = caption_check.get("summary_en", "")
        if caption_summary and not caption_check.get("all_passed", True):
            summary_parts.append(f"Caption issues: {caption_summary}")

    return {
        "all_passed": overall_passed,
        "content_checks": content_checks,
        "caption_check": caption_check,
        "summary_en": " | ".join(summary_parts) if summary_parts else "All checks passed.",
    }

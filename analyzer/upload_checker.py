from __future__ import annotations

import json
import re

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from models.guideline import ParsedGuideline


UPLOAD_CHECK_PROMPT = """You are checking a PUBLISHED social media post to verify that all required caption elements are present.

You are given:
1. The guideline's mandatory elements (hashtags, mentions, disclosures, links, etc.)
2. The actual post content (scraped from the URL)

Check for:
- All required #hashtags are present (exact match, case-insensitive)
- All required @mentions are present
- Required disclosure text (e.g., "AD", "광고", "Sponsored", "#ad") is present
- Any required links or CTAs in the caption
- Post is set to correct visibility (if detectable)

Return ONLY valid JSON:
{{
  "all_passed": true/false,
  "checks": [
    {{
      "element": "the required element",
      "status": "found|missing|partial",
      "detail": "where it was found or what's wrong"
    }}
  ],
  "summary_ko": "Korean summary of results",
  "summary_en": "English summary of results"
}}
"""


def check_upload(post_content: str, guideline: ParsedGuideline) -> dict:
    """Check if a published post meets caption/hashtag requirements.

    Args:
        post_content: The scraped post text/caption
        guideline: The parsed guideline with mandatory elements

    Returns:
        Dict with check results
    """
    # Filter for caption-related mandatory elements
    caption_elements = []
    for elem in guideline.mandatory_elements:
        if any(p in elem.lower() for p in ["#", "@", "hashtag", "mention", "ad", "광고", "sponsored", "disclosure"]):
            caption_elements.append(elem)

    # Also check rules for caption-related requirements
    for rule in guideline.rules:
        desc_lower = rule.description.lower()
        if any(p in desc_lower for p in ["#", "@", "hashtag", "mention", "caption", "bio", "link"]):
            caption_elements.append(rule.description)

    if not caption_elements:
        return {
            "all_passed": True,
            "checks": [],
            "summary_ko": "가이드라인에 캡션 관련 필수 요소가 없습니다.",
            "summary_en": "No caption-related mandatory elements in the guideline.",
        }

    # Quick local check first (fast, no API needed)
    local_results = []
    all_local_pass = True
    for elem in caption_elements:
        # Extract hashtags and mentions from element description
        hashtags = re.findall(r"#\w+", elem)
        mentions = re.findall(r"@\w+", elem)

        for tag in hashtags:
            found = tag.lower() in post_content.lower()
            local_results.append({
                "element": tag,
                "status": "found" if found else "missing",
                "detail": f"캡션에서 {'발견됨' if found else '발견되지 않음'}",
            })
            if not found:
                all_local_pass = False

        for mention in mentions:
            found = mention.lower() in post_content.lower()
            local_results.append({
                "element": mention,
                "status": "found" if found else "missing",
                "detail": f"캡션에서 {'발견됨' if found else '발견되지 않음'}",
            })
            if not found:
                all_local_pass = False

    # Check for ad disclosure
    ad_keywords = ["#ad", "#광고", "광고 포함", "sponsored", "paid partnership"]
    has_ad_requirement = any("ad" in e.lower() or "광고" in e.lower() or "disclosure" in e.lower() for e in caption_elements)
    if has_ad_requirement:
        ad_found = any(kw.lower() in post_content.lower() for kw in ad_keywords)
        local_results.append({
            "element": "광고 표시 (Ad Disclosure)",
            "status": "found" if ad_found else "missing",
            "detail": f"캡션에서 {'발견됨' if ad_found else '발견되지 않음'}",
        })
        if not ad_found:
            all_local_pass = False

    if local_results:
        missing = [r for r in local_results if r["status"] == "missing"]
        found = [r for r in local_results if r["status"] == "found"]
        summary_ko = f"총 {len(local_results)}개 항목 중 {len(found)}개 확인, {len(missing)}개 누락"
        summary_en = f"{len(found)} of {len(local_results)} items found, {len(missing)} missing"
        if missing:
            summary_ko += "\n누락 항목: " + ", ".join(r["element"] for r in missing)
            summary_en += "\nMissing: " + ", ".join(r["element"] for r in missing)

        return {
            "all_passed": all_local_pass,
            "checks": local_results,
            "summary_ko": summary_ko,
            "summary_en": summary_en,
        }

    # If no specific hashtags/mentions found in element text, use AI
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    content = [
        {
            "type": "text",
            "text": (
                f"=== MANDATORY CAPTION ELEMENTS ===\n"
                + "\n".join(f"- {e}" for e in caption_elements)
                + f"\n\n=== POST CONTENT ===\n{post_content}\n\n"
                + UPLOAD_CHECK_PROMPT
            ),
        }
    ]

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        temperature=0,
        messages=[{"role": "user", "content": content}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)

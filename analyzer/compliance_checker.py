from __future__ import annotations

import base64
import json
import math
import re
import time
from typing import List, Optional

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from models.guideline import ParsedGuideline
from models.review_result import ReviewReport, SceneReview, RuleReview, EditingTip
from processors.video_processor import ProcessedVideo

# Social media caption items - excluded from video review
CAPTION_PATTERNS = [
    r"@\w+",           # @mentions
    r"#\w+",           # #hashtags
    r"hashtag",
    r"mention",
]


def _is_caption_item(text: str) -> bool:
    """Check if a mandatory element is a social media caption item (not video content)."""
    text_lower = text.lower()
    for pattern in CAPTION_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


BATCH_ANALYSIS_PROMPT = """You are analyzing a BATCH of video frames for content compliance review.

You are given:
1. The guideline summary
2. A batch of consecutive video frames with timestamps and transcript

For EACH frame, describe what you see in detail:
- What is visible (people, products, text overlays, angles, lighting)
- What action is happening
- Any products shown and how they are displayed
- Camera angle (close-up, medium, wide, etc.)

Return ONLY valid JSON:
{
  "frame_analyses": [
    {
      "timestamp": 0.0,
      "description": "Detailed description of what is visible in this frame",
      "products_visible": ["product names if any"],
      "camera_angle": "close-up|medium|wide|etc",
      "text_overlay": "any on-screen text or null",
      "action": "what is happening"
    }
  ]
}
"""

FINAL_REVIEW_PROMPT = """You are an expert video content compliance reviewer doing a FINAL comprehensive review.

You are given:
1. The full parsed guideline (rules, scenes, mandatory elements)
2. The guideline's original reference images
3. DETAILED frame-by-frame analysis of the ENTIRE video (every 0.8-1.5 seconds)
4. The full transcript (STT)
{memo_section}

YOUR TASK: Using the detailed frame analysis, perform a thorough compliance check.

=== CRITICAL REVIEW GUIDELINES ===

**IMPORTANT - What to EXCLUDE from review:**
- @mentions and #hashtags are for the SOCIAL MEDIA POST CAPTION, NOT the video.
- Do NOT include @mentions or #hashtags in mandatory_check or rule_reviews.
- Only review what is actually IN the video content.

**Scene Compliance (be FAIR and SPECIFIC):**
- Use the frame-by-frame analysis to find where each guideline scene is fulfilled in the video.
- Scenes do NOT need to appear in the exact guideline order — creators often reorder for their style.
- If the scene's INTENT is fulfilled (similar content, similar message), mark as pass even if execution differs slightly.
- For "before/after": look for any visual comparison, not necessarily split screen.
- For "product showcase": product visible at any point counts.
- Cite specific timestamps as evidence (e.g. "2.4초에 두 제품을 함께 보여줌").

**EVIDENCE/SOURCE CITATION (CRITICAL):**
- In ALL findings and evidence fields, you MUST include specific timestamps AND transcript quotes.
- Format: [X.X초] "해당 시점의 스크립트 인용" — 설명
- Example: [2.4초] "이 제품 진짜 좋아요" — 제품을 손에 들고 보여주는 장면
- If no speech at that timestamp, write: [2.4초] (음성 없음) — 설명
- This helps the reviewer pinpoint exact moments in the original video.

**B&A (Before/After) REVIEW:**
- B&A scenes are DIFFICULT to judge from static frames alone.
- If the guideline requires B&A and the video appears to have a B&A section:
  - Check for: split screen, "before"/"after" text overlays, clear visual contrast
  - If you can clearly see distinct before/after states → judge normally
  - If you CANNOT confidently determine the quality of the B&A contrast → mark as "warning" and add to manual_review_flags
- Always add B&A items to manual_review_flags with a specific description of what needs human verification.

**Script/Voice-over Compliance (be FLEXIBLE):**
- Script suggestions are SUGGESTIONS. Similar message in creator's own words = compliant.
- Only flag if the KEY MESSAGE is completely absent.

**Rule Compliance:**
- DO rules: Generally followed = compliant.
- DON'T rules: Strictly checked.
- BRAND RULES (STRICT): Check transcript for forbidden words. Critical.
{memo_rules_section}

**IMPORTANT - Frame Analysis Limitations:**
- Static frames cannot capture everything (motion, transitions, quick cuts).
- If you CANNOT confirm something from the frames, do NOT assume it's missing — mark as "warning" instead of "fail".
- Only mark "fail" when you have CLEAR evidence of non-compliance.
- When in doubt, give the creator the benefit of the doubt.

**Scoring (be FAIR — most creator videos score 70-95):**
- 90-100: All key scenes present, all strict rules followed, strong overall compliance
- 80-89: Most scenes present, no strict violations, minor gaps only
- 70-79: Key scenes present but some improvements needed, no critical violations
- 55-69: Several scenes missing or notable violations
- Below 55: Major non-compliance (very rare for submitted videos)

**Status thresholds:**
- "approved": score >= 85
- "revision_needed": score 55-84
- "rejected": score < 55

Return ONLY valid JSON:
{{
  "overall_score": 85,
  "overall_status": "approved|revision_needed|rejected",
  "summary": "2-3 sentence overall assessment in Korean",
  "scene_reviews": [
    {{
      "scene_number": 1,
      "status": "pass|fail|warning",
      "guideline_description": "What the guideline required",
      "matched_time_range": "0-3s",
      "findings": "Detailed findings in Korean. MUST include [X.X초] \\"transcript quote\\" format for every claim. Example: [1.6초] \\"피부가 달라졌어요\\" — 클로즈업으로 얼굴을 보여주며 변화를 설명",
      "suggestion": "Specific revision suggestion in Korean (empty string if pass)"
    }}
  ],
  "rule_reviews": [
    {{
      "rule_category": "do|dont|brand_rule|mandatory",
      "rule_description": "The rule (EXCLUDE @mention and #hashtag rules)",
      "status": "compliant|violated|unclear",
      "evidence": "Specific evidence with [X.X초] \\"transcript\\" format",
      "suggestion": "Revision suggestion in Korean (empty string if compliant)"
    }}
  ],
  "mandatory_check": {{
    "element_name (EXCLUDE mentions and hashtags)": true
  }},
  "revision_items": [
    "Concise revision item in Korean (video edits only)"
  ],
  "manual_review_flags": [
    "Items that AI cannot confidently judge and need human eyes. E.g.: B&A 장면(4.0-8.0초)의 비포/애프터 차이 정도를 육안으로 확인 필요"
  ],
  "editing_tips": [
    {{
      "scene_number": 1,
      "category": "font|effect|transition|layout|sfx|general",
      "tip": ["구체적 편집 팁 1 (한국어)", "구체적 편집 팁 2", "..."],
      "capcut_how": "캡컷 탐색 경로. 예: 텍스트 → 폰트 → 검색: noto",
      "font_names": ["폰트 이름 (해당 시에만)", "예: Noto Sans KR", "나눔손글씨 붓"],
      "sfx_names": ["SFX 이름 (해당 시에만)", "예: Cartoon → Scribble", "Transition → Swoosh 2"]
    }}
  ],
  "email_draft": "Professional revision request email in Korean.\\nInclude:\\n- Greeting\\n- What was done well\\n- Specific revision items\\n- Closing"
}}

IMPORTANT:
- Be thorough but FAIR. Most creator submissions are genuine attempts that score 70+.
- Do NOT penalize for things you cannot confirm from static frames — use "warning" status instead.
- STRICT brand rules must be enforced strictly.
- All output in Korean.
- Do NOT include @mentions or #hashtags in any review results.
- ALWAYS cite sources with [초수] "스크립트" format in findings and evidence.
- editing_tips: Generate 5-12 practical CapCut editing tips. Each tip must be actionable.
  - "tip" is a LIST of bullet points. Each bullet = one concrete action. Include values where helpful:
    - Colors: "흰색", "빨간색 계열" (hex optional)
    - Sizes/positions: "화면 절반 이상", "세로 중앙 배치"
    - CapCut features: "인 → 팝업(Pop)", "인 → 타이핑(Typewriter)"
  - "capcut_how": Navigation path in CapCut, e.g. "텍스트 → 폰트" or "스티커 탭 → 검색: scribble"
  - "font_names": Use GENERAL font style descriptions, NOT specific font names. e.g. ["고딕체 Bold", "산세리프 Regular", "손글씨 스타일"]. Empty list if not font category.
  - "sfx_names": Use CapCut SFX category paths. e.g. ["Cartoon 카테고리", "Transition 카테고리"]. Empty list if no SFX.
  - Categories to cover: 기본 자막, 강조 텍스트, 특수효과/스티커, 레이아웃, 전환, 효과음 등
  - Think like a CapCut power user teaching a beginner creator.
"""


def _build_frame_content_for_batch(frames) -> list:
    """Build Claude API content blocks for a batch of frames."""
    content = []
    for frame in frames:
        b64 = base64.b64encode(frame.image_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })
        label = f"[{frame.timestamp:.1f}s] STT: \"{frame.transcript_text}\""
        content.append({"type": "text", "text": label})
    return content


def _build_guideline_images_content(guideline_images: list) -> list:
    """Build Claude API content blocks for guideline reference images."""
    content = []
    for i, img_bytes in enumerate(guideline_images):
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })
        content.append({"type": "text", "text": f"[Guideline page {i + 1}]"})
    return content


def _call_claude_with_retry(client, content, max_tokens=8192, max_retries=5):
    """Call Claude API with adaptive exponential backoff on rate limit."""
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                temperature=0,
                messages=[{"role": "user", "content": content}],
            )
            return response
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                wait_time = min(30 * (2 ** attempt), 300)  # 30s, 60s, 120s, 240s, cap 300s
                time.sleep(wait_time)
            else:
                raise


def _parse_json_response(text: str) -> dict:
    """Parse JSON from Claude response, handling markdown wrapping."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


def run_compliance_check(
    guideline: ParsedGuideline,
    guideline_images: list,
    video: ProcessedVideo,
    progress_callback=None,
    memo: str = "",
) -> ReviewReport:
    """Run compliance check with ALL frames via batched analysis.

    Phase 1: Analyze ALL frames in batches (8 frames per batch, 65s wait between)
    Phase 2: Final comprehensive review using all frame analyses + guideline
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    guideline_json = guideline.model_dump_json(indent=2)
    total_frames = len(video.frames)
    frames_per_batch = 8

    # Filter out caption items from mandatory elements for review
    video_mandatory = [e for e in guideline.mandatory_elements if not _is_caption_item(e)]
    caption_mandatory = [e for e in guideline.mandatory_elements if _is_caption_item(e)]

    # Split frames into batches
    batches = []
    for i in range(0, total_frames, frames_per_batch):
        batches.append(video.frames[i:i + frames_per_batch])

    num_batches = len(batches)
    total_steps = num_batches + 2  # batches + final review + done

    if progress_callback:
        progress_callback(0, total_steps,
                          f"전체 {total_frames}프레임을 {num_batches}배치로 분석합니다...")

    # --- Phase 1: Batch frame analysis ---
    all_frame_analyses = []

    for batch_idx, batch in enumerate(batches):
        if progress_callback:
            progress_callback(
                batch_idx, total_steps,
                f"배치 {batch_idx + 1}/{num_batches} 분석 중... "
                f"({batch[0].timestamp:.1f}s ~ {batch[-1].timestamp:.1f}s)"
            )

        # Small polite delay between batches (skip first)
        if batch_idx > 0:
            time.sleep(3)

        batch_content = []
        batch_content.append({
            "type": "text",
            "text": f"=== GUIDELINE SUMMARY ===\n{guideline_json}",
        })
        batch_content.append({
            "type": "text",
            "text": f"\n=== VIDEO FRAMES (batch {batch_idx + 1}/{num_batches}) ===",
        })
        batch_content.extend(_build_frame_content_for_batch(batch))
        batch_content.append({"type": "text", "text": BATCH_ANALYSIS_PROMPT})

        batch_response = _call_claude_with_retry(client, batch_content, max_tokens=4096)
        batch_result = _parse_json_response(batch_response.content[0].text)
        all_frame_analyses.extend(batch_result.get("frame_analyses", []))

    # --- Phase 2: Final comprehensive review ---
    if progress_callback:
        progress_callback(
            num_batches, total_steps,
            "최종 종합 검수 중 (rate limit 대기 포함)..."
        )

    time.sleep(3)

    # Build memo sections for prompt
    memo_section = ""
    memo_rules_section = ""
    if memo:
        memo_section = f"\n5. Additional notes/memos from the reviewer:\n{memo}"
        memo_rules_section = f"\n\n**REVIEWER MEMO (IMPORTANT - overrides guideline where applicable):**\n{memo}\n- If the memo says a certain requirement is waived, mark it as compliant."

    final_prompt = FINAL_REVIEW_PROMPT.format(
        memo_section=memo_section,
        memo_rules_section=memo_rules_section,
    )

    final_content = []

    # Guideline images (limit to 4)
    limited_images = guideline_images[:4] if len(guideline_images) > 4 else guideline_images
    final_content.append({"type": "text", "text": "=== GUIDELINE REFERENCE IMAGES ==="})
    final_content.extend(_build_guideline_images_content(limited_images))

    final_content.append({
        "type": "text",
        "text": f"\n=== PARSED GUIDELINE ===\n{guideline_json}",
    })

    # Filtered mandatory elements (video-only)
    if video_mandatory:
        final_content.append({
            "type": "text",
            "text": f"\n=== VIDEO MANDATORY ELEMENTS (check these) ===\n"
                    + "\n".join(f"- {e}" for e in video_mandatory),
        })
    if caption_mandatory:
        final_content.append({
            "type": "text",
            "text": f"\n=== CAPTION ITEMS (DO NOT review, for post upload only) ===\n"
                    + "\n".join(f"- {e}" for e in caption_mandatory),
        })

    # Frame-by-frame analysis
    final_content.append({
        "type": "text",
        "text": f"\n=== DETAILED FRAME-BY-FRAME ANALYSIS ({len(all_frame_analyses)} frames) ===\n"
                + json.dumps(all_frame_analyses, indent=2, ensure_ascii=False),
    })

    # Full transcript
    final_content.append({
        "type": "text",
        "text": f"\n=== FULL TRANSCRIPT ===\n{video.full_transcript}",
    })

    final_content.append({"type": "text", "text": final_prompt})

    final_response = _call_claude_with_retry(client, final_content, max_tokens=8192)
    result = _parse_json_response(final_response.content[0].text)

    if progress_callback:
        progress_callback(total_steps, total_steps, "검수 완료!")

    # Filter out any caption items that slipped through in mandatory_check
    filtered_mandatory = {}
    for key, val in (result.get("mandatory_check") or {}).items():
        if not _is_caption_item(key):
            filtered_mandatory[key] = val

    # Filter out caption-related rule reviews
    filtered_rules = []
    for r in (result.get("rule_reviews") or []):
        if not _is_caption_item(r.get("rule_description", "")):
            filtered_rules.append(r)

    report = ReviewReport(
        overall_score=result.get("overall_score") or 0,
        overall_status=result.get("overall_status") or "revision_needed",
        summary=result.get("summary") or "",
        scene_reviews=[SceneReview(**s) for s in (result.get("scene_reviews") or [])],
        rule_reviews=[RuleReview(**r) for r in filtered_rules],
        mandatory_check=filtered_mandatory,
        revision_items=result.get("revision_items") or [],
        email_draft=result.get("email_draft") or "",
        manual_review_flags=[str(f) for f in (result.get("manual_review_flags") or [])],
        editing_tips=[
            EditingTip(**{
                **t,
                # Normalize tip: ensure it's always a list
                "tip": t["tip"] if isinstance(t.get("tip"), list) else [t["tip"]] if t.get("tip") else [],
                "font_names": t.get("font_names") or [],
                "sfx_names": t.get("sfx_names") or [],
            })
            for t in (result.get("editing_tips") or [])
        ],
    )

    return report

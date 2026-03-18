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
from models.review_result import ReviewReport, SceneReview, RuleReview, EditingTip, RevisionComparison
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
  "email_draft": "SKIP - will be generated separately"
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


EMAIL_GENERATION_PROMPT = """You are a professional influencer campaign manager writing a revision request email to a creator.

You are given:
1. The review results (score, status, scene reviews, rule violations, revision items)
2. The guideline title and product name
3. (If available) Comparison with previous review round — what was fixed and what still needs work

=== COMMUNICATION PRINCIPLES ===

**Tone:**
- Warm, collaborative, and respectful — the creator is a valued partner, not an employee
- Start by genuinely acknowledging what they did well (be specific, not generic)
- Frame revisions as "small adjustments to make the content even better" not "things you did wrong"
- Use encouraging language: "~하면 더 좋을 것 같아요", "~부분만 살짝 수정 부탁드려요"
- End with enthusiasm about the final result

**Structure:**
- Greeting (friendly, use 크리에이터님 or the tone appropriate for each language)
- If this is a RE-REVIEW (round 2+): acknowledge the effort they put into revisions, specifically mention what they fixed well
- Genuine compliment on specific strong points (cite actual scenes/moments)
- Clear revision items — numbered, specific, actionable
  - For each item: what to change + WHY with guideline reference + how (if applicable)
  - Distinguish between MUST-FIX (가이드라인 필수) and NICE-TO-HAVE (권장)
- If reshoot is needed: be empathetic, explain why it's necessary, offer flexibility
- Timeline/next steps
- Warm closing

**PUSHBACK-PROOF WRITING (CRITICAL):**
- For EVERY revision item, cite the specific guideline requirement. Example:
  - Korean: "가이드라인 Scene 3에 따르면 '제품 클로즈업 5초 이상' 이 필요한데, 현재 약 2초 정도로 확인됩니다."
  - English: "Per the guideline (Scene 3), a 5+ second product close-up is required, but the current version shows approximately 2 seconds."
- Pre-emptively explain the REASON behind the requirement when it might seem arbitrary:
  - "이 부분은 브랜드사에서 특히 중요하게 보는 항목이라 꼭 반영 부탁드려요"
  - "This is a key requirement from the brand to ensure regulatory compliance"
- For subjective items, use softened language and offer alternatives:
  - "이 부분은 이렇게 수정하시거나, 혹은 다른 방식으로 표현해주셔도 괜찮습니다"
- If an item has been requested before (re-review), be firmer but still respectful:
  - "이전에도 안내드렸던 부분인데, 이번에도 동일하게 확인됩니다. 가이드라인 필수 사항이라 꼭 수정 부탁드립니다."

**Revision severity levels (include in both languages):**
- 🔴 필수 수정 (Must fix): Guideline violations that must be corrected
- 🟡 권장 수정 (Recommended): Would improve the content but not strictly required
- 🟢 참고 사항 (FYI): Minor notes for future reference

**For RESHOOT scenarios:**
- Be extra empathetic: "촬영을 다시 부탁드리게 되어 정말 죄송합니다"
- Clearly explain what specifically needs reshooting and why
- Suggest ways to minimize reshoot effort (e.g., "해당 장면만 다시 촬영해주시면 됩니다")

=== OUTPUT FORMAT ===
Return ONLY valid JSON:
{{
  "email_ko": "Full Korean email with proper line breaks (use \\n for newlines)",
  "email_en": "Full English email with proper line breaks (use \\n for newlines)"
}}

Generate both versions. The English version should NOT be a direct translation — adapt the tone and phrasing naturally for English-speaking creators while keeping the same information.
"""


BRAND_SHEET_PROMPT = """You are generating a concise review comment for a brand review sheet.
This comment will be pasted into a shared spreadsheet/document for the brand team to review.

Given the review results, generate a structured comment in this format:

**Korean version:**
[검수 결과] 점수: XX/100 | 상태: 수정필요/승인/반려
---
✅ 잘된 점:
- (specific positive point with timestamp)

❌ 수정 필요:
1. [XX:XX] (issue description) — 가이드라인 Scene X 기준
2. [XX:XX] (issue description) — 가이드라인 규칙 위반

⚠️ 확인 필요:
- (items needing brand's judgment)

**English version:**
Same structure but in English.

Return ONLY valid JSON:
{{
  "comment_ko": "Full Korean comment (use \\n for newlines)",
  "comment_en": "Full English comment (use \\n for newlines)"
}}
"""


def _generate_revision_email(
    client,
    report: ReviewReport,
    guideline: ParsedGuideline,
    previous_report: Optional[ReviewReport] = None,
    review_round: int = 1,
) -> tuple[str, str]:
    """Generate polished revision emails in Korean and English.

    Returns (email_ko, email_en).
    """
    # Build context for email generation
    review_summary = {
        "score": report.overall_score,
        "status": report.overall_status,
        "summary": report.summary,
        "revision_items": report.revision_items,
        "review_round": review_round,
        "scene_issues": [
            {
                "scene": sr.scene_number,
                "status": sr.status,
                "time": sr.matched_time_range,
                "findings": sr.findings,
                "suggestion": sr.suggestion,
            }
            for sr in report.scene_reviews
            if sr.status in ("fail", "warning")
        ],
        "rule_violations": [
            {
                "category": rr.rule_category,
                "rule": rr.rule_description,
                "status": rr.status,
                "evidence": rr.evidence,
                "suggestion": rr.suggestion,
            }
            for rr in report.rule_reviews
            if rr.status in ("violated", "unclear")
        ],
        "passed_scenes": [
            {
                "scene": sr.scene_number,
                "time": sr.matched_time_range,
                "findings": sr.findings,
            }
            for sr in report.scene_reviews
            if sr.status == "pass"
        ],
        "needs_reshoot": report.overall_score < 55,
    }

    # Add comparison with previous review if available
    comparison_section = ""
    if previous_report and review_round > 1:
        comparison = _compare_reviews(previous_report, report)
        review_summary["comparison"] = [c.model_dump() for c in comparison]
        comparison_section = (
            f"\n=== COMPARISON WITH PREVIOUS REVIEW (Round {review_round - 1} → {review_round}) ===\n"
            f"Previous score: {previous_report.overall_score} → Current score: {report.overall_score}\n"
            f"{json.dumps([c.model_dump() for c in comparison], ensure_ascii=False, indent=2)}\n"
        )

    # Add guideline rules for citation
    guideline_rules_text = "\n=== GUIDELINE RULES (for citation in email) ===\n"
    for rule in guideline.rules:
        guideline_rules_text += f"- [{rule.category}] {rule.description} (severity: {rule.severity})\n"
    for scene in guideline.scenes:
        guideline_rules_text += f"- [Scene {scene.scene_number}] {scene.description}"
        if scene.time_range:
            guideline_rules_text += f" ({scene.time_range})"
        guideline_rules_text += "\n"

    content = [
        {
            "type": "text",
            "text": (
                f"=== GUIDELINE INFO ===\n"
                f"Title: {guideline.title}\n"
                f"Product: {guideline.product_name}\n"
                f"Concept: {guideline.concept}\n"
                f"{guideline_rules_text}"
                f"\n=== REVIEW RESULTS ===\n"
                f"{json.dumps(review_summary, ensure_ascii=False, indent=2)}\n"
                f"{comparison_section}"
                f"\n{EMAIL_GENERATION_PROMPT}"
            ),
        }
    ]

    response = _call_claude_with_retry(client, content, max_tokens=4096)
    result = _parse_json_response(response.content[0].text)

    return result.get("email_ko", ""), result.get("email_en", "")


def _generate_brand_sheet_comment(
    client,
    report: ReviewReport,
    guideline: ParsedGuideline,
) -> tuple[str, str]:
    """Generate formatted comments for brand review sheet.

    Returns (comment_ko, comment_en).
    """
    review_data = {
        "score": report.overall_score,
        "status": report.overall_status,
        "summary": report.summary,
        "scene_reviews": [
            {
                "scene": sr.scene_number,
                "status": sr.status,
                "time": sr.matched_time_range,
                "findings": sr.findings,
                "suggestion": sr.suggestion,
                "guideline_description": sr.guideline_description,
            }
            for sr in report.scene_reviews
        ],
        "rule_violations": [
            {
                "category": rr.rule_category,
                "rule": rr.rule_description,
                "status": rr.status,
                "evidence": rr.evidence,
                "suggestion": rr.suggestion,
            }
            for rr in report.rule_reviews
            if rr.status in ("violated", "unclear")
        ],
        "manual_review_flags": report.manual_review_flags,
        "revision_items": report.revision_items,
    }

    content = [
        {
            "type": "text",
            "text": (
                f"=== GUIDELINE: {guideline.title} ({guideline.product_name}) ===\n"
                f"\n=== REVIEW RESULTS ===\n"
                f"{json.dumps(review_data, ensure_ascii=False, indent=2)}\n"
                f"\n{BRAND_SHEET_PROMPT}"
            ),
        }
    ]

    response = _call_claude_with_retry(client, content, max_tokens=2048)
    result = _parse_json_response(response.content[0].text)

    return result.get("comment_ko", ""), result.get("comment_en", "")


def _compare_reviews(previous: ReviewReport, current: ReviewReport) -> list[RevisionComparison]:
    """Compare current review with previous review to find what was fixed."""
    comparisons = []

    # Compare scene reviews
    prev_scenes = {sr.scene_number: sr for sr in previous.scene_reviews}
    curr_scenes = {sr.scene_number: sr for sr in current.scene_reviews}

    for scene_num, prev_sr in prev_scenes.items():
        if prev_sr.status in ("fail", "warning"):
            curr_sr = curr_scenes.get(scene_num)
            if curr_sr:
                if curr_sr.status == "pass":
                    status = "fixed"
                elif curr_sr.status == "warning" and prev_sr.status == "fail":
                    status = "partially_fixed"
                else:
                    status = "still_pending"
            else:
                status = "fixed"

            comparisons.append(RevisionComparison(
                item=f"Scene {scene_num}: {prev_sr.guideline_description}",
                status=status,
                previous_finding=prev_sr.findings,
                current_finding=curr_sr.findings if curr_sr else "",
            ))

    # Compare rule violations
    prev_violations = {rr.rule_description: rr for rr in previous.rule_reviews if rr.status == "violated"}
    curr_rules = {rr.rule_description: rr for rr in current.rule_reviews}

    for rule_desc, prev_rr in prev_violations.items():
        curr_rr = curr_rules.get(rule_desc)
        if curr_rr:
            if curr_rr.status == "compliant":
                status = "fixed"
            elif curr_rr.status == "unclear":
                status = "partially_fixed"
            else:
                status = "still_pending"
        else:
            status = "fixed"

        comparisons.append(RevisionComparison(
            item=f"Rule: {rule_desc}",
            status=status,
            previous_finding=prev_rr.evidence,
            current_finding=curr_rr.evidence if curr_rr else "",
        ))

    # Compare revision items by similarity
    prev_items = set(previous.revision_items)
    curr_items = set(current.revision_items)
    for item in prev_items:
        if item not in curr_items:
            # Check if any current item is similar
            still_there = any(_text_similarity(item, ci) > 0.5 for ci in curr_items)
            comparisons.append(RevisionComparison(
                item=item,
                status="still_pending" if still_there else "fixed",
                previous_finding=item,
                current_finding="",
            ))

    return comparisons


def _text_similarity(a: str, b: str) -> float:
    """Simple word overlap similarity."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a), len(words_b))


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
    previous_report: Optional[ReviewReport] = None,
    review_round: int = 1,
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
    total_steps = num_batches + 4  # batches + final review + email generation + brand sheet + done

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

    # --- Phase 3: Generate revision emails (if not approved) ---
    email_ko = ""
    email_en = ""
    brand_comment_ko = ""
    brand_comment_en = ""
    revision_comparison = []
    status = result.get("overall_status", "revision_needed")

    # Build a temporary report for generation
    temp_report = ReviewReport(
        overall_score=result.get("overall_score") or 0,
        overall_status=status,
        summary=result.get("summary") or "",
        scene_reviews=[SceneReview(**s) for s in (result.get("scene_reviews") or [])],
        rule_reviews=[RuleReview(**r) for r in (result.get("rule_reviews") or [])],
        revision_items=result.get("revision_items") or [],
    )

    # Compare with previous review if available
    if previous_report:
        revision_comparison = _compare_reviews(previous_report, temp_report)

    if status != "approved":
        if progress_callback:
            progress_callback(
                num_batches + 1, total_steps,
                "수정 안내 이메일 생성 중 (한국어/영어)..."
            )
        time.sleep(2)

        try:
            email_ko, email_en = _generate_revision_email(
                client, temp_report, guideline,
                previous_report=previous_report,
                review_round=review_round,
            )
        except Exception:
            email_ko = result.get("email_draft") or ""
            email_en = ""

    # --- Phase 3.5: Generate brand sheet comment ---
    if progress_callback:
        progress_callback(
            num_batches + 2, total_steps,
            "브랜드사 전달용 코멘트 생성 중..."
        )
    time.sleep(2)

    try:
        brand_comment_ko, brand_comment_en = _generate_brand_sheet_comment(
            client, temp_report, guideline
        )
    except Exception:
        brand_comment_ko = ""
        brand_comment_en = ""

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
        email_draft=email_ko or result.get("email_draft") or "",
        email_draft_en=email_en,
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
        brand_sheet_comment=brand_comment_ko,
        brand_sheet_comment_en=brand_comment_en,
        revision_comparison=revision_comparison,
        review_round=review_round,
    )

    return report

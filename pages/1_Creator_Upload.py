"""Creator self-service upload & review page.

Creators can:
1. Select their campaign (from saved guidelines)
2. Enter their name
3. Paste a Google Drive link OR upload a video file
4. Get automatic review results
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ANTHROPIC_API_KEY, OPENAI_API_KEY
from models.guideline import ParsedGuideline
from models.review_result import ReviewReport
import db

st.set_page_config(
    page_title="Video Review Upload",
    page_icon="📤",
    layout="wide",
)

# --- i18n ---
TEXTS = {
    "ko": {
        "hero_title": "영상 검수 업로드",
        "hero_desc": "영상을 업로드하면 가이드라인 준수 여부를 자동으로 검수합니다.",
        "no_campaign": "등록된 캠페인이 없습니다. 관리자에게 문의해주세요.",
        "step1_label": "캠페인",
        "step1_title": "캠페인 선택",
        "step2_title": "크리에이터 정보",
        "step2_placeholder": "예: @creator_name",
        "step3_title": "영상 업로드",
        "upload_gdrive": "Google Drive 링크",
        "upload_file": "파일 직접 업로드",
        "upload_method": "업로드 방식",
        "gdrive_placeholder": "https://drive.google.com/file/d/.../view 형태의 링크 붙여넣기",
        "gdrive_help": "파일이 **'링크가 있는 모든 사람'**으로 공유되어 있어야 합니다.\nGoogle Drive에서 파일 우클릭 → 공유 → '링크가 있는 모든 사람'으로 변경",
        "video_file": "영상 파일",
        "api_error": "시스템 설정 오류입니다. 관리자에게 문의해주세요.",
        "enter_name": "이름/채널명을 입력해주세요.",
        "upload_video": "영상 파일을 업로드하거나 Google Drive 링크를 붙여넣어주세요.",
        "start_review": "검수 시작",
        "prev_found": "이전 검수 이력 발견! Round {round}로 진행합니다.",
        "preparing": "준비 중...",
        "downloading": "Google Drive에서 영상 다운로드 중...",
        "dl_progress": "다운로드 중... {dl:.0f}/{total:.0f} MB",
        "dl_progress_nosize": "다운로드 중... {dl:.0f} MB",
        "dl_done": "다운로드 완료: {name} ({size}MB)",
        "invalid_gdrive": "올바른 Google Drive 링크가 아닙니다.",
        "analyzing": "영상 분석 중 (프레임 추출 + 음성 인식)...",
        "done": "검수 완료!",
        "error": "오류 발생: {e}",
        "result_title": "검수 결과",
        "status_approved": "승인 — 수정 없이 게시 가능합니다!",
        "status_revision": "수정 필요 — 아래 항목을 확인해주세요.",
        "status_rejected": "반려 — 가이드라인을 재확인 후 다시 촬영해주세요.",
        "summary": "요약",
        "issues_title": "수정이 필요한 부분",
        "fix_method": "수정 방법",
        "guideline_label": "가이드라인",
        "passed_title": "통과 항목 ({n}개)",
        "revision_title": "이전 검수 대비 변경사항 (Round {round})",
        "fixed": "수정 완료 ({n}건)",
        "partial": "부분 수정 ({n}건)",
        "pending": "아직 미수정 ({n}건)",
        "tips_title": "편집 가이드",
        "tips_scene": "장면",
        "tips_category": "카테고리",
        "tips_tip": "편집 팁",
        "tips_font": "캡컷 폰트",
        "tips_sfx": "캡컷 SFX",
        "tips_dl": "📥 편집 가이드 다운로드 (.txt)",
        "tips_dl_header": "🎨 편집 가이드 (캡컷 기준)",
        "checklist_title": "수정 체크리스트",
        "contact": "검수 결과에 대한 문의는 담당자에게 연락해주세요.",
        "guideline_summary": "가이드라인 요약 보기",
        "product": "제품",
        "concept": "컨셉",
        "duration": "영상 길이",
        "key_message": "키 메시지",
        "scene_count": "장면 수",
        "mandatory": "필수 요소",
        "cat_font": "폰트/자막",
        "cat_effect": "효과/이펙트",
        "cat_transition": "전환/트랜지션",
        "cat_layout": "레이아웃/구도",
        "cat_sfx": "사운드/효과음",
        "cat_general": "일반 편집",
        "scene_all": "전체",
        "history_title": "내 검수 이력",
        "history_empty": "이전 검수 이력이 없습니다.",
        "history_round": "Round {round}",
        "history_score": "점수",
        "history_status": "상태",
        "history_date": "검수일시",
        "history_detail": "상세 보기",
        "status_map_approved": "✅ 승인",
        "status_map_revision": "📝 수정 필요",
        "status_map_rejected": "❌ 반려",
        "status_map_pending": "⏳ 대기",
        "next_steps_title": "다음 단계",
        "next_step_1": "승인된 영상을 SNS 플랫폼에 업로드해주세요.",
        "next_step_2": "업로드 후 게시물 링크를 아래에 붙여넣어주세요.",
        "next_step_3": "해시태그와 캡션이 가이드라인에 맞는지 자동으로 확인합니다.",
        "post_link_placeholder": "https://www.instagram.com/p/... 또는 https://www.tiktok.com/@.../video/...",
        "submit_link": "링크 제출",
        "link_submitted": "링크가 제출되었습니다! 담당자가 확인 후 연락드리겠습니다.",
        "link_empty": "게시물 링크를 입력해주세요.",
        "caption_check_title": "캡션 검수",
        "caption_check_desc": "게시물의 해시태그, 멘션, 광고 표시 등이 가이드라인에 맞는지 확인합니다.",
        "caption_input_url": "게시물 URL",
        "caption_input_paste": "캡션 직접 붙여넣기",
        "caption_input_mode": "입력 방식",
        "caption_url_placeholder": "YouTube, Instagram, TikTok 게시물 링크",
        "caption_url_help": "지원: YouTube, Instagram, TikTok (공개 게시물)",
        "caption_paste_placeholder": "게시물의 캡션/설명을 여기에 붙여넣으세요.\n\n예:\n오늘도 피부 관리! #광고 #skincare @brandname ...",
        "caption_check_btn": "🔍 캡션 검수 시작",
        "caption_fetching": "게시물 캡션 가져오는 중...",
        "caption_fetched": "{platform}에서 캡션을 가져왔습니다.",
        "caption_fetched_content": "가져온 캡션 내용",
        "caption_checking": "캡션 필수 요소 확인 중...",
        "caption_all_pass": "모든 필수 요소가 확인되었습니다!",
        "caption_missing": "누락된 항목이 있습니다. 수정 후 다시 확인해주세요.",
        "caption_check_error": "확인 오류: {e}",
        "caption_summary": "요약",
        "caption_no_input": "게시물 URL 또는 캡션을 입력해주세요.",
        "brand_feedback_title": "브랜드 피드백",
        "brand_feedback_desc": "고객사(브랜드)로부터 전달된 피드백입니다. 아래 내용을 반영하여 수정해주세요.",
        "brand_feedback_round": "라운드 {round}",
        "brand_feedback_date": "전달일시",
        "brand_feedback_empty": "전달된 브랜드 피드백이 없습니다.",
        "admin_approved": "✅ 어드민 최종 승인",
        "admin_auto_approved": "🤖 자동 승인 (90점+)",
        "admin_revision": "📝 어드민 수정 요청",
        "admin_rejected": "❌ 어드민 반려",
        "admin_memo_label": "어드민 메모",
        "step_upload": "영상 업로드",
        "step_ai_review": "AI 검수",
        "step_admin": "어드민 확인",
        "step_caption": "캡션 검수",
        "step_done": "완료",
        "new_feedback_alert": "💬 새로운 브랜드 피드백이 있습니다! 아래에서 확인하세요.",
        "priority_high": "🔴 필수 수정",
        "priority_medium": "🟡 권장 수정",
        "priority_low": "🟢 참고",
    },
    "en": {
        "hero_title": "Video Review Upload",
        "hero_desc": "Upload your video and get automatic guideline compliance review.",
        "no_campaign": "No campaigns found. Please contact your manager.",
        "step1_label": "Campaign",
        "step1_title": "Select Campaign",
        "step2_title": "Creator Info",
        "step2_placeholder": "e.g. @creator_name",
        "step3_title": "Upload Video",
        "upload_gdrive": "Google Drive Link",
        "upload_file": "Direct File Upload",
        "upload_method": "Upload method",
        "gdrive_placeholder": "Paste a link like https://drive.google.com/file/d/.../view",
        "gdrive_help": "The file must be shared as **'Anyone with the link'**.\nIn Google Drive: right-click → Share → Change to 'Anyone with the link'",
        "video_file": "Video file",
        "api_error": "System configuration error. Please contact your manager.",
        "enter_name": "Please enter your name or channel name.",
        "upload_video": "Please upload a video file or paste a Google Drive link.",
        "start_review": "Start Review",
        "prev_found": "Previous review found! Proceeding as Round {round}.",
        "preparing": "Preparing...",
        "downloading": "Downloading video from Google Drive...",
        "dl_progress": "Downloading... {dl:.0f}/{total:.0f} MB",
        "dl_progress_nosize": "Downloading... {dl:.0f} MB",
        "dl_done": "Download complete: {name} ({size}MB)",
        "invalid_gdrive": "Invalid Google Drive link.",
        "analyzing": "Analyzing video (frame extraction + speech recognition)...",
        "done": "Review complete!",
        "error": "Error: {e}",
        "result_title": "Review Results",
        "status_approved": "Approved — ready to publish!",
        "status_revision": "Revision needed — please check the items below.",
        "status_rejected": "Rejected — please re-check the guidelines and re-shoot.",
        "summary": "Summary",
        "issues_title": "Issues to Fix",
        "fix_method": "How to fix",
        "guideline_label": "Guideline",
        "passed_title": "Passed Items ({n})",
        "revision_title": "Changes vs. Previous Review (Round {round})",
        "fixed": "Fixed ({n})",
        "partial": "Partially Fixed ({n})",
        "pending": "Still Pending ({n})",
        "tips_title": "Editing Guide",
        "tips_scene": "Scene",
        "tips_category": "Category",
        "tips_tip": "Editing Tips",
        "tips_font": "CapCut Fonts",
        "tips_sfx": "CapCut SFX",
        "tips_dl": "📥 Download Editing Guide (.txt)",
        "tips_dl_header": "🎨 Editing Guide (CapCut)",
        "checklist_title": "Revision Checklist",
        "contact": "For questions about the review, please contact your manager.",
        "guideline_summary": "View Guideline Summary",
        "product": "Product",
        "concept": "Concept",
        "duration": "Video Duration",
        "key_message": "Key Message",
        "scene_count": "Scenes",
        "mandatory": "Required Elements",
        "cat_font": "Font/Subtitle",
        "cat_effect": "Effect",
        "cat_transition": "Transition",
        "cat_layout": "Layout",
        "cat_sfx": "Sound/SFX",
        "cat_general": "General",
        "scene_all": "Overall",
        "history_title": "My Review History",
        "history_empty": "No previous reviews found.",
        "history_round": "Round {round}",
        "history_score": "Score",
        "history_status": "Status",
        "history_date": "Date",
        "history_detail": "View Details",
        "status_map_approved": "✅ Approved",
        "status_map_revision": "📝 Revision Needed",
        "status_map_rejected": "❌ Rejected",
        "status_map_pending": "⏳ Pending",
        "next_steps_title": "Next Steps",
        "next_step_1": "Upload the approved video to your SNS platform.",
        "next_step_2": "Paste the post link below after uploading.",
        "next_step_3": "We'll automatically check your hashtags and caption against the guidelines.",
        "post_link_placeholder": "https://www.instagram.com/p/... or https://www.tiktok.com/@.../video/...",
        "submit_link": "Submit Link",
        "link_submitted": "Link submitted! Your manager will review and follow up.",
        "link_empty": "Please enter your post link.",
        "caption_check_title": "Caption Check",
        "caption_check_desc": "Verify that your post's hashtags, mentions, and ad disclosure meet the guidelines.",
        "caption_input_url": "Post URL",
        "caption_input_paste": "Paste Caption",
        "caption_input_mode": "Input method",
        "caption_url_placeholder": "YouTube, Instagram, or TikTok post link",
        "caption_url_help": "Supported: YouTube, Instagram, TikTok (public posts)",
        "caption_paste_placeholder": "Paste the caption/description of your post here.\n\ne.g.:\nSkincare routine! #ad #skincare @brandname ...",
        "caption_check_btn": "🔍 Check Caption",
        "caption_fetching": "Fetching post caption...",
        "caption_fetched": "Caption fetched from {platform}.",
        "caption_fetched_content": "Fetched caption",
        "caption_checking": "Checking required caption elements...",
        "caption_all_pass": "All required elements verified!",
        "caption_missing": "Some items are missing. Please fix and check again.",
        "caption_check_error": "Check error: {e}",
        "caption_summary": "Summary",
        "caption_no_input": "Please enter a post URL or paste the caption.",
        "brand_feedback_title": "Brand Feedback",
        "brand_feedback_desc": "Feedback from the brand/client. Please incorporate these changes in your revision.",
        "brand_feedback_round": "Round {round}",
        "brand_feedback_date": "Date",
        "brand_feedback_empty": "No brand feedback received.",
        "admin_approved": "✅ Admin Approved",
        "admin_auto_approved": "🤖 Auto-Approved (90+)",
        "admin_revision": "📝 Admin Revision Requested",
        "admin_rejected": "❌ Admin Rejected",
        "admin_memo_label": "Admin Memo",
        "step_upload": "Upload",
        "step_ai_review": "AI Review",
        "step_admin": "Admin Check",
        "step_caption": "Caption Check",
        "step_done": "Done",
        "new_feedback_alert": "💬 New brand feedback received! Check below.",
        "priority_high": "🔴 Must Fix",
        "priority_medium": "🟡 Suggested",
        "priority_low": "🟢 FYI",
    },
}


def t(key: str, **kwargs) -> str:
    """Get translated text."""
    lang = st.session_state.get("creator_lang", "ko")
    text = TEXTS.get(lang, TEXTS["ko"]).get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text


# --- Custom CSS ---
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; max-width: 800px; }

    .creator-hero {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px; padding: 32px 40px; color: #fff;
        margin-bottom: 24px; text-align: center;
    }
    .creator-hero h1 { font-size: 28px; margin-bottom: 8px; }
    .creator-hero p { font-size: 14px; color: #e0d4f5; margin: 0; }

    .lang-toggle {
        position: absolute; top: 12px; right: 16px;
        z-index: 10;
    }

    .step-card {
        background: #f8fafc; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 20px 24px;
        margin-bottom: 16px;
    }
    .step-num {
        display: inline-flex; align-items: center; justify-content: center;
        width: 28px; height: 28px; border-radius: 50%;
        background: #667eea; color: #fff; font-weight: 700;
        font-size: 14px; margin-right: 10px;
    }
    .step-title { font-size: 16px; font-weight: 600; color: #1e293b; }

    .result-card {
        border-radius: 12px; padding: 20px 24px;
        margin-bottom: 12px;
    }
    .result-pass {
        background: #f0fdf4; border: 1px solid #bbf7d0;
        border-left: 4px solid #22c55e;
    }
    .result-fail {
        background: #fef2f2; border: 1px solid #fecaca;
        border-left: 4px solid #ef4444;
    }
    .result-warn {
        background: #fffbeb; border: 1px solid #fde68a;
        border-left: 4px solid #f59e0b;
    }

    .score-display {
        font-size: 72px; font-weight: 800; text-align: center;
        margin: 16px 0 8px 0; line-height: 1;
    }
    .score-high { color: #22c55e; }
    .score-mid { color: #f59e0b; }
    .score-low { color: #ef4444; }
    .score-label {
        text-align: center; font-size: 14px; color: #64748b;
        margin-bottom: 20px;
    }

    /* ===== Editing Tips Table (matching admin) ===== */
    .tips-wrap { margin-top: 16px; }
    .tips-table {
        border-collapse: collapse; width: 100%; background: #fff;
        border-radius: 12px; overflow: hidden;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }
    .tips-table thead tr { background: #1a1a1a; color: #fff; }
    .tips-table thead th {
        padding: 14px 16px; text-align: left; font-size: 11px;
        font-weight: 600; letter-spacing: 0.6px; text-transform: uppercase;
        white-space: nowrap;
    }
    .tips-table tbody tr { border-bottom: 1px solid #f0f0f0; transition: background 0.15s; }
    .tips-table tbody tr:last-child { border-bottom: none; }
    .tips-table tbody tr:hover { background: #fafaf8; }
    .tips-table td { padding: 16px; vertical-align: top; font-size: 13px; line-height: 1.6; }
    .tips-table .thumb {
        width: 70px; height: 124px; object-fit: cover;
        border-radius: 8px; display: block; background: #f0f0f0;
    }
    .tips-table .thumb-placeholder {
        width: 70px; height: 124px; border-radius: 8px;
        background: #f0f0f0; display: flex; align-items: center;
        justify-content: center; font-size: 11px; color: #bbb;
    }
    .tag-tip {
        display: inline-block; padding: 2px 10px; border-radius: 20px;
        font-size: 11px; font-weight: 600; margin-bottom: 4px;
    }
    .tag-font   { background: #e8f4e8; color: #2d7a2d; }
    .tag-effect { background: #fdf0e0; color: #b05c00; }
    .tag-transition { background: #f3e8f8; color: #7a2d9a; }
    .tag-layout { background: #e8eef8; color: #2450a0; }
    .tag-sfx    { background: #fff3cd; color: #7a5200; }
    .tag-general{ background: #f0f0f0; color: #555; }
    .tip-scene-label { font-weight: 700; font-size: 13px; margin-bottom: 2px; }
    .tip-scene-time { font-size: 11px; color: #888; }
    .font-chip {
        display: inline-block; background: #f0f0f0; border: 1px solid #ddd;
        color: #333; border-radius: 5px; padding: 2px 8px; font-size: 12px;
        font-weight: 600; margin: 2px 2px 2px 0; font-family: monospace;
    }
    .sfx-badge {
        display: inline-block; background: #fff3cd; border: 1px solid #ffc107;
        color: #7a5200; border-radius: 5px; padding: 2px 8px; font-size: 12px;
        font-weight: 600; margin: 2px 2px 2px 0;
    }
    .tip-list { list-style: none; padding: 0; margin: 0; }
    .tip-list li {
        padding: 2px 0 2px 14px; position: relative;
        font-size: 12.5px; color: #333;
    }
    .tip-list li::before {
        content: "→"; position: absolute; left: 0;
        color: #bbb; font-size: 11px; top: 4px;
    }
    .capcut-path-inline { font-size: 11px; color: #999; margin-top: 4px; }
    .capcut-path-inline .pa { color: #ccc; margin: 0 3px; }
    .td-empty { color: #ddd; text-align: center; }

    /* ===== Step Indicator ===== */
    .step-indicator {
        display: flex; align-items: center; justify-content: center;
        gap: 0; margin: 0 auto 24px auto; max-width: 600px;
    }
    .step-dot {
        width: 32px; height: 32px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 13px; font-weight: 700; flex-shrink: 0;
    }
    .step-dot-done { background: #22c55e; color: #fff; }
    .step-dot-active { background: #667eea; color: #fff; box-shadow: 0 0 0 4px rgba(102,126,234,0.3); }
    .step-dot-pending { background: #e2e8f0; color: #94a3b8; }
    .step-line { flex: 1; height: 3px; min-width: 20px; }
    .step-line-done { background: #22c55e; }
    .step-line-pending { background: #e2e8f0; }
    .step-label {
        font-size: 10px; text-align: center; margin-top: 4px;
        color: #64748b; white-space: nowrap;
    }
    .step-item { display: flex; flex-direction: column; align-items: center; }

    /* ===== Alert Badge ===== */
    .feedback-alert {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        border: 1px solid #f59e0b; border-radius: 12px;
        padding: 12px 20px; margin-bottom: 16px;
        font-size: 14px; font-weight: 600; color: #92400e;
    }
    .admin-badge {
        display: inline-block; padding: 4px 12px; border-radius: 20px;
        font-size: 12px; font-weight: 700; margin: 4px 2px;
    }
    .admin-badge-approved { background: #dcfce7; color: #166534; }
    .admin-badge-auto { background: #dbeafe; color: #1e40af; }
    .admin-badge-revision { background: #fef3c7; color: #92400e; }
    .admin-badge-rejected { background: #fee2e2; color: #991b1b; }
</style>
""", unsafe_allow_html=True)

# --- Language Toggle ---
if "creator_lang" not in st.session_state:
    st.session_state["creator_lang"] = "ko"

lang_col1, lang_col2 = st.columns([8, 1])
with lang_col2:
    lang_options = {"한국어": "ko", "English": "en"}
    current_label = "한국어" if st.session_state["creator_lang"] == "ko" else "English"
    selected_lang = st.selectbox(
        "🌐",
        list(lang_options.keys()),
        index=list(lang_options.values()).index(st.session_state["creator_lang"]),
        key="lang_selector",
        label_visibility="collapsed",
    )
    if lang_options[selected_lang] != st.session_state["creator_lang"]:
        st.session_state["creator_lang"] = lang_options[selected_lang]
        st.rerun()

# --- Hero ---
st.markdown(
    '<div class="creator-hero">'
    f'<h1>{t("hero_title")}</h1>'
    f'<p>{t("hero_desc")}</p>'
    '</div>',
    unsafe_allow_html=True,
)


# --- Helper: compute current workflow phase ---
def _compute_phase(history: list[dict]) -> int:
    """Return phase 1-5 based on review history.
    1=Upload, 2=AI Review done, 3=Admin checked, 4=Caption done, 5=All done
    """
    if not history:
        return 1
    latest = history[0]  # newest first
    ad = latest.get("admin_decision")
    cap = latest.get("caption_check_result")
    status = latest.get("overall_status", "")
    if cap and isinstance(cap, dict) and cap.get("all_passed"):
        return 5  # all done
    if ad in ("approved", "auto_approved"):
        return 4  # ready for caption
    if ad:
        return 3  # admin decided (revision/rejected)
    if status:
        return 2  # AI review done, waiting admin
    return 1


def _render_step_indicator(phase: int):
    """Render the 5-step progress indicator."""
    steps = [
        t("step_upload"), t("step_ai_review"), t("step_admin"),
        t("step_caption"), t("step_done"),
    ]
    parts = []
    for i, label in enumerate(steps):
        step_num = i + 1
        if step_num < phase:
            dot_cls = "step-dot-done"
            icon = "✓"
        elif step_num == phase:
            dot_cls = "step-dot-active"
            icon = str(step_num)
        else:
            dot_cls = "step-dot-pending"
            icon = str(step_num)
        parts.append(
            f'<div class="step-item">'
            f'<div class="step-dot {dot_cls}">{icon}</div>'
            f'<div class="step-label">{label}</div></div>'
        )
        if i < len(steps) - 1:
            line_cls = "step-line-done" if step_num < phase else "step-line-pending"
            parts.append(f'<div class="step-line {line_cls}"></div>')
    st.markdown(
        f'<div class="step-indicator">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


# --- Read URL params (for pre-filled links) ---
params = st.query_params
param_campaign = params.get("campaign", "")
param_creator = params.get("creator", "")

# --- Step 1: Campaign Selection ---
campaigns = db.list_guidelines()
if not campaigns:
    st.warning(t("no_campaign"))
    st.stop()

campaign_names = [row["campaign_name"] for row in campaigns]

if param_campaign and param_campaign in campaign_names:
    selected_campaign = param_campaign
    st.markdown(
        f'<div class="step-card">'
        f'<span class="step-num">1</span>'
        f'<span class="step-title">{t("step1_label")}: {selected_campaign}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div class="step-card">'
        '<span class="step-num">1</span>'
        f'<span class="step-title">{t("step1_title")}</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    selected_campaign = st.selectbox(
        t("step1_label"),
        campaign_names,
        key="creator_campaign_select",
        label_visibility="collapsed",
    )

# Load selected guideline
selected_row = next(row for row in campaigns if row["campaign_name"] == selected_campaign)
campaign_name, guideline = db.load_guideline(selected_row["id"])

# Show brief guideline info
with st.expander(t("guideline_summary"), expanded=False):
    st.markdown(f"**{t('product')}:** {guideline.product_name}")
    st.markdown(f"**{t('concept')}:** {guideline.concept}")
    st.markdown(f"**{t('duration')}:** {guideline.video_duration}")
    if guideline.key_message:
        st.markdown(f"**{t('key_message')}:** {guideline.key_message}")
    if guideline.scenes:
        st.markdown(f"**{t('scene_count')}:** {len(guideline.scenes)}")
    if guideline.mandatory_elements:
        st.markdown(f"**{t('mandatory')}:**")
        for elem in guideline.mandatory_elements:
            st.markdown(f"  - {elem}")

# --- Step 2: Creator Info ---
if param_creator:
    creator_name = param_creator
    st.markdown(
        f'<div class="step-card">'
        f'<span class="step-num">2</span>'
        f'<span class="step-title">{t("step2_title")}: {creator_name}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div class="step-card">'
        '<span class="step-num">2</span>'
        f'<span class="step-title">{t("step2_title")}</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    creator_name = st.text_input(
        t("step2_title"),
        placeholder=t("step2_placeholder"),
        key="creator_self_name",
        label_visibility="collapsed",
    )

# --- Step 3: Video Upload ---
st.markdown(
    '<div class="step-card">'
    '<span class="step-num">3</span>'
    f'<span class="step-title">{t("step3_title")}</span>'
    '</div>',
    unsafe_allow_html=True,
)

upload_method = st.radio(
    t("upload_method"),
    [t("upload_gdrive"), t("upload_file")],
    horizontal=True,
    key="creator_upload_method",
)

gdrive_url = ""
video_files = None

if upload_method == t("upload_gdrive"):
    gdrive_url = st.text_input(
        t("upload_gdrive"),
        placeholder=t("gdrive_placeholder"),
        key="creator_gdrive_url",
    )
    st.caption(t("gdrive_help"))
else:
    video_files = st.file_uploader(
        t("video_file"),
        type=["mp4", "mov", "avi", "mkv"],
        accept_multiple_files=False,
        key="creator_video_upload",
        label_visibility="collapsed",
    )

# --- API Check ---
api_ok = bool(ANTHROPIC_API_KEY and OPENAI_API_KEY)
if not api_ok:
    st.error(t("api_error"))

# --- Start Review ---
has_video = bool(gdrive_url.strip()) or bool(video_files)
has_name = bool(creator_name.strip())

if not has_name:
    st.info(t("enter_name"))
elif not has_video:
    st.info(t("upload_video"))

# --- Review History + Step Indicator ---
_history = []
if has_name:
    _campaign_id = guideline.title or guideline.product_name or "default"
    _history = db.get_creator_reviews(_campaign_id, creator_name.strip())

    # Step indicator
    current_phase = _compute_phase(_history)
    _render_step_indicator(current_phase)

    # New feedback alert
    _fb_reviews = [r for r in _history if r.get("brand_feedback")]
    if _fb_reviews:
        st.markdown(f'<div class="feedback-alert">{t("new_feedback_alert")}</div>', unsafe_allow_html=True)

    # Admin decision alert (latest)
    if _history:
        _latest_ad = _history[0].get("admin_decision")
        _ad_labels = {
            "approved": ("admin_approved", "admin-badge-approved"),
            "auto_approved": ("admin_auto_approved", "admin-badge-auto"),
            "revision_needed": ("admin_revision", "admin-badge-revision"),
            "rejected": ("admin_rejected", "admin-badge-rejected"),
        }
        if _latest_ad and _latest_ad in _ad_labels:
            _lbl_key, _badge_cls = _ad_labels[_latest_ad]
            st.markdown(
                f'<div class="admin-badge {_badge_cls}">{t(_lbl_key)}</div>',
                unsafe_allow_html=True,
            )
            if _history[0].get("admin_memo"):
                st.caption(f"{t('admin_memo_label')}: {_history[0]['admin_memo']}")

    if _history:
        with st.expander(f"📋 {t('history_title')} ({len(_history)})", expanded=False):
            status_map = {
                "approved": t("status_map_approved"),
                "revision_needed": t("status_map_revision"),
                "rejected": t("status_map_rejected"),
            }
            _ad_map = {
                "approved": "✅",
                "auto_approved": "🤖",
                "revision_needed": "📝",
                "rejected": "❌",
            }
            for row in _history:
                sc = row.get("overall_score", 0)
                score_color = "#22c55e" if sc >= 80 else ("#f59e0b" if sc >= 60 else "#ef4444")
                st_label = status_map.get(row.get("overall_status", ""), t("status_map_pending"))
                ts = row["created_at"][:16].replace("T", " ") if row.get("created_at") else ""
                ad_icon = _ad_map.get(row.get("admin_decision", ""), "")
                fb_icon = "💬" if row.get("brand_feedback") else ""
                cap_icon = ""
                _cap = row.get("caption_check_result")
                if _cap and isinstance(_cap, dict):
                    cap_icon = "🔗✅" if _cap.get("all_passed") else "🔗❌"
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:12px;padding:8px 12px;'
                    f'border-bottom:1px solid #f0f0f0;">'
                    f'<span style="font-weight:700;min-width:70px;">'
                    f'{t("history_round", round=row.get("round", 1))}</span>'
                    f'<span style="color:{score_color};font-weight:800;font-size:18px;min-width:40px;">'
                    f'{sc}</span>'
                    f'<span style="min-width:80px;">{st_label}</span>'
                    f'<span style="font-size:14px;">{ad_icon} {fb_icon} {cap_icon}</span>'
                    f'<span style="color:#94a3b8;font-size:12px;">{ts}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

review_btn = st.button(
    t("start_review"),
    disabled=not (has_video and has_name and api_ok),
    use_container_width=True,
    type="primary",
    key="creator_review_btn",
)

if review_btn and has_video and has_name and api_ok:
    from processors.video_processor import process_video
    from analyzer.compliance_checker import run_compliance_check

    campaign_id = guideline.title or guideline.product_name or "default"
    c_name = creator_name.strip()

    # Get previous review for comparison
    previous_report = None
    current_round = 1
    prev = db.get_previous_review(campaign_id, c_name)
    if prev:
        previous_report, prev_round = prev
        current_round = prev_round + 1
        st.info(t("prev_found", round=current_round))

    progress = st.progress(0, text=t("preparing"))

    try:
        # --- Download from Google Drive if needed ---
        if gdrive_url.strip() and not video_files:
            from utils.gdrive_video import download_gdrive_video, is_gdrive_url

            if not is_gdrive_url(gdrive_url.strip()):
                st.error(t("invalid_gdrive"))
                st.stop()

            progress.progress(5, text=t("downloading"))

            def dl_progress(dl_mb, total_mb):
                if total_mb:
                    pct = min(int((dl_mb / total_mb) * 20) + 5, 25)
                    progress.progress(pct, text=t("dl_progress", dl=dl_mb, total=total_mb))
                else:
                    progress.progress(15, text=t("dl_progress_nosize", dl=dl_mb))

            filename, tmp_path = download_gdrive_video(gdrive_url.strip(), dl_progress)
            video_bytes = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)
            st.success(t("dl_done", name=filename, size=len(video_bytes) // (1024*1024)))
        else:
            filename = str(video_files.name)
            video_bytes = video_files.read()

        # --- Process video ---
        progress.progress(25, text=t("analyzing"))
        processed_video = process_video(video_bytes, str(filename))

        # --- Run compliance check ---
        guideline_images = []  # Creator page doesn't have guideline images in session

        def update_progress(step, total, msg):
            pct = 30 + int((step / total) * 65)
            progress.progress(min(pct, 95), text=msg)

        report = run_compliance_check(
            guideline=guideline,
            guideline_images=guideline_images,
            video=processed_video,
            progress_callback=update_progress,
            previous_report=previous_report,
            review_round=current_round,
        )

        # Save review history
        db.save_review(campaign_id, c_name, report, current_round)

        progress.progress(100, text=t("done"))
        st.session_state["creator_report"] = report
        st.session_state["creator_processed_video"] = processed_video

    except Exception as e:
        progress.empty()
        st.error(t("error", e=e))
        import traceback
        st.code(traceback.format_exc())

# --- Display Results ---
if "creator_report" in st.session_state:
    import base64 as _b64
    import re as _re

    report: ReviewReport = st.session_state["creator_report"]

    st.divider()
    st.markdown(f"## {t('result_title')}")

    # Score display
    score = report.overall_score
    score_class = "score-high" if score >= 80 else ("score-mid" if score >= 60 else "score-low")
    status_labels = {
        "approved": t("status_approved"),
        "revision_needed": t("status_revision"),
        "rejected": t("status_rejected"),
    }
    status_label = status_labels.get(report.overall_status, "—")
    status_icons = {"approved": "✅", "revision_needed": "📝", "rejected": "❌"}

    st.markdown(
        f'<div class="score-display {score_class}">{score}</div>'
        f'<div class="score-label">{status_icons.get(report.overall_status, "")} {status_label}</div>',
        unsafe_allow_html=True,
    )

    # Summary
    st.markdown(f"**{t('summary')}:** {report.summary}")

    # --- Issues (sorted by severity: fail first, then warning) ---
    problem_scenes = sorted(
        [sr for sr in report.scene_reviews if sr.status in ("fail", "warning")],
        key=lambda s: (0 if s.status == "fail" else 1),
    )
    violated_rules = [r for r in report.rule_reviews if r.status == "violated"]

    if problem_scenes or violated_rules:
        # Priority summary card
        n_fail = sum(1 for s in problem_scenes if s.status == "fail") + len(violated_rules)
        n_warn = sum(1 for s in problem_scenes if s.status == "warning")
        if n_fail > 0:
            st.markdown(
                f'<div class="result-card result-fail" style="text-align:center;">'
                f'{t("priority_high")} <b>{n_fail}</b>건'
                + (f'&nbsp;&nbsp;{t("priority_medium")} <b>{n_warn}</b>건' if n_warn else '')
                + f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown(f"### {t('issues_title')}")

        for sr in problem_scenes:
            icon = "❌" if sr.status == "fail" else "⚠️"
            card_class = "result-fail" if sr.status == "fail" else "result-warn"
            time_info = f" ({sr.matched_time_range})" if sr.matched_time_range else ""

            suggestion_html = ""
            if sr.suggestion:
                suggestion_html = f"<br><strong>{t('fix_method')}:</strong> {sr.suggestion}"

            st.markdown(
                f'<div class="result-card {card_class}">'
                f'<strong>{icon} Scene {sr.scene_number}{time_info}</strong><br>'
                f'<span style="color:#6b7280;font-size:13px;">{t("guideline_label")}: {sr.guideline_description}</span><br>'
                f'{sr.findings}'
                f'{suggestion_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        for r in violated_rules:
            st.markdown(
                f'<div class="result-card result-fail">'
                f'<strong>❌ [{r.rule_category}] {r.rule_description}</strong><br>'
                f'{r.evidence}<br>'
                f'<strong>{t("fix_method")}:</strong> {r.suggestion}'
                f'</div>',
                unsafe_allow_html=True,
            )

    # --- Passed items ---
    passed_scenes = [sr for sr in report.scene_reviews if sr.status == "pass"]
    if passed_scenes:
        with st.expander(f"✅ {t('passed_title', n=len(passed_scenes))}", expanded=False):
            for sr in passed_scenes:
                st.markdown(f"- ✅ Scene {sr.scene_number}: {sr.findings[:100]}")

    # --- Revision comparison (for re-reviews) ---
    if report.revision_comparison:
        st.markdown(f"### {t('revision_title', round=report.review_round)}")

        fixed = [c for c in report.revision_comparison if c.status == "fixed"]
        partial = [c for c in report.revision_comparison if c.status == "partially_fixed"]
        pending = [c for c in report.revision_comparison if c.status == "still_pending"]

        if fixed:
            st.markdown(f"**✅ {t('fixed', n=len(fixed))}**")
            for c in fixed:
                st.markdown(f"- ~~{c.item}~~")

        if partial:
            st.markdown(f"**🟡 {t('partial', n=len(partial))}**")
            for c in partial:
                st.markdown(f"- {c.item}")

        if pending:
            st.markdown(f"**❌ {t('pending', n=len(pending))}**")
            for c in pending:
                st.markdown(f"- {c.item}")

    # --- Editing Tips (rich table, matching admin) ---
    if report.editing_tips:
        st.markdown(f"### 🎨 {t('tips_title')}")

        category_names = {
            "font": t("cat_font"),
            "effect": t("cat_effect"),
            "transition": t("cat_transition"),
            "layout": t("cat_layout"),
            "sfx": t("cat_sfx"),
            "general": t("cat_general"),
        }

        # Build scene→thumbnail mapping from video frames
        scene_thumbs = {}
        processed_video = st.session_state.get("creator_processed_video")
        if processed_video and report.scene_reviews:
            for sr in report.scene_reviews:
                m = _re.search(r"([\d.]+)\s*[-~]\s*([\d.]+)", sr.matched_time_range or "")
                if m:
                    t_start = float(m.group(1))
                    t_mid = (t_start + float(m.group(2))) / 2
                else:
                    t_mid = None

                if t_mid is not None and processed_video.frames:
                    best_frame = min(
                        processed_video.frames,
                        key=lambda f: abs(f.timestamp - t_mid),
                    )
                    scene_thumbs[sr.scene_number] = _b64.b64encode(
                        best_frame.image_bytes
                    ).decode("utf-8")

        # Build table HTML
        html = ['<div class="tips-wrap"><table class="tips-table">']
        html.append(
            "<thead><tr>"
            f"<th>{t('tips_scene')}</th>"
            f"<th>{t('tips_category')}</th>"
            f"<th>{t('tips_tip')}</th>"
            f"<th>{t('tips_font')}</th>"
            f"<th>{t('tips_sfx')}</th>"
            "</tr></thead><tbody>"
        )

        for tip in report.editing_tips:
            cat = tip.category
            tag_class = f"tag-{cat}" if cat in category_names else "tag-general"
            cat_label = category_names.get(cat, cat)
            scene_num = tip.scene_number
            scene_label = f"Scene {scene_num}" if scene_num > 0 else t("scene_all")

            td_thumb = '<td style="width:100px;text-align:center;">'
            if scene_num in scene_thumbs:
                td_thumb += (
                    f'<img class="thumb" '
                    f'src="data:image/jpeg;base64,{scene_thumbs[scene_num]}" />'
                )
            else:
                td_thumb += '<div class="thumb-placeholder">—</div>'
            td_thumb += f'<div class="tip-scene-label">{scene_label}</div>'
            sr_match = next(
                (sr for sr in report.scene_reviews if sr.scene_number == scene_num),
                None,
            )
            if sr_match and sr_match.matched_time_range:
                td_thumb += f'<div class="tip-scene-time">{sr_match.matched_time_range}</div>'
            td_thumb += "</td>"

            td_cat = (
                f'<td><span class="tag-tip {tag_class}">{cat_label}</span></td>'
            )

            td_tip = "<td>"
            tip_items = tip.tip if isinstance(tip.tip, list) else [tip.tip]
            if tip_items:
                td_tip += '<ul class="tip-list">'
                for item in tip_items:
                    td_tip += f"<li>{item}</li>"
                td_tip += "</ul>"
            if tip.capcut_how:
                path_fmt = tip.capcut_how.replace(
                    " > ", ' <span class="pa">›</span> '
                ).replace(
                    " → ", ' <span class="pa">›</span> '
                )
                td_tip += f'<div class="capcut-path-inline">{path_fmt}</div>'
            td_tip += "</td>"

            if tip.font_names:
                td_font = "<td>" + " ".join(
                    f'<span class="font-chip">{f}</span>' for f in tip.font_names
                )
                if tip.capcut_how and cat == "font":
                    path_fmt = tip.capcut_how.replace(" > ", " › ").replace(" → ", " › ")
                    td_font += f'<div class="capcut-path-inline">{path_fmt}</div>'
                td_font += "</td>"
            else:
                td_font = '<td class="td-empty">—</td>'

            if tip.sfx_names:
                td_sfx = "<td>" + " ".join(
                    f'<span class="sfx-badge">{s}</span>' for s in tip.sfx_names
                ) + "</td>"
            else:
                td_sfx = '<td class="td-empty">—</td>'

            html.append(
                f"<tr>{td_thumb}{td_cat}{td_tip}{td_font}{td_sfx}</tr>"
            )

        html.append("</tbody></table></div>")

        st.markdown("".join(html), unsafe_allow_html=True)

        st.markdown("")

        # Download as text
        tips_text = t("tips_dl_header") + "\n" + "=" * 40 + "\n\n"
        for tip in report.editing_tips:
            scene_label = f"Scene {tip.scene_number}" if tip.scene_number > 0 else t("scene_all")
            tips_text += f"[{scene_label}] [{category_names.get(tip.category, tip.category)}]\n"
            tip_items = tip.tip if isinstance(tip.tip, list) else [tip.tip]
            for item in tip_items:
                tips_text += f"  → {item}\n"
            if tip.font_names:
                tips_text += f"  Font: {', '.join(tip.font_names)}\n"
            if tip.sfx_names:
                tips_text += f"  SFX: {', '.join(tip.sfx_names)}\n"
            if tip.capcut_how:
                tips_text += f"  CapCut: {tip.capcut_how}\n"
            tips_text += "\n"

        st.download_button(
            label=t("tips_dl"),
            data=tips_text,
            file_name="editing_tips.txt",
            mime="text/plain",
        )

    # --- Revision items summary ---
    if report.revision_items:
        st.divider()
        st.markdown(f"### {t('checklist_title')}")
        for i, item in enumerate(report.revision_items, 1):
            st.checkbox(item, key=f"creator_checklist_{i}")

    # --- Brand Feedback (shown after results, not before upload) ---
    if has_name and _fb_reviews:
        st.divider()
        st.markdown(f"### 💬 {t('brand_feedback_title')}")
        st.caption(t("brand_feedback_desc"))
        for fb_rev in _fb_reviews:
            fb_ts = fb_rev["created_at"][:16].replace("T", " ") if fb_rev.get("created_at") else ""
            st.markdown(
                f'<div class="result-card result-warn">'
                f'<strong>{t("brand_feedback_round", round=fb_rev.get("round", 1))}</strong>'
                f' <span style="color:#94a3b8;font-size:12px;">({fb_ts})</span><br>'
                f'{fb_rev["brand_feedback"]}'
                f'</div>',
                unsafe_allow_html=True,
            )

    # --- Next Steps (for approved videos — AI or admin approved) ---
    _is_approved = (
        report.overall_status == "approved"
        or (has_name and _history and _history[0].get("admin_decision") in ("approved", "auto_approved"))
    )
    if _is_approved:
        st.divider()
        st.markdown(f"### 🚀 {t('next_steps_title')}")
        st.markdown(
            f'<div class="result-card result-pass">'
            f'<strong>1.</strong> {t("next_step_1")}<br>'
            f'<strong>2.</strong> {t("next_step_2")}<br>'
            f'<strong>3.</strong> {t("next_step_3")}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # --- Caption Self-Check ---
        st.markdown(f"### 🔍 {t('caption_check_title')}")
        st.caption(t("caption_check_desc"))

        caption_mode = st.radio(
            t("caption_input_mode"),
            [t("caption_input_url"), t("caption_input_paste")],
            horizontal=True,
            key="creator_caption_mode",
        )

        caption_url = ""
        caption_text = ""

        if caption_mode == t("caption_input_url"):
            caption_url = st.text_input(
                t("caption_input_url"),
                placeholder=t("caption_url_placeholder"),
                key="creator_caption_url",
            )
            st.caption(t("caption_url_help"))
        else:
            caption_text = st.text_area(
                t("caption_input_paste"),
                placeholder=t("caption_paste_placeholder"),
                height=200,
                key="creator_caption_text",
            )

        has_caption_input = bool(caption_url.strip()) or bool(caption_text.strip())
        caption_btn = st.button(
            t("caption_check_btn"),
            disabled=not has_caption_input,
            use_container_width=True,
            key="creator_caption_btn",
        )

        if caption_btn and has_caption_input:
            from analyzer.upload_checker import check_upload, fetch_post_content

            post_content = caption_text.strip()

            # Fetch content from URL if needed
            if caption_url.strip() and not post_content:
                with st.spinner(t("caption_fetching")):
                    try:
                        platform, fetched = fetch_post_content(caption_url.strip())
                        post_content = fetched
                        st.success(f"✅ {t('caption_fetched', platform=platform)}")
                        with st.expander(t("caption_fetched_content"), expanded=False):
                            st.text(post_content[:2000])
                    except ValueError as e:
                        st.error(str(e))
                        post_content = ""

            if post_content:
                with st.spinner(t("caption_checking")):
                    try:
                        cap_result = check_upload(post_content, guideline)
                        st.session_state["creator_caption_result"] = cap_result
                        # Save to DB
                        if has_name and _history:
                            db.save_caption_check(_history[0]["id"], cap_result)
                    except Exception as e:
                        st.error(t("caption_check_error", e=e))

        if "creator_caption_result" in st.session_state:
            cap_result = st.session_state["creator_caption_result"]
            all_ok = cap_result.get("all_passed", False)

            if all_ok:
                st.success(f"✅ {t('caption_all_pass')}")
            else:
                st.warning(f"⚠️ {t('caption_missing')}")

            checks = cap_result.get("checks", [])
            if checks:
                for chk in checks:
                    status = chk.get("status", "")
                    element = chk.get("element", "")
                    detail = chk.get("detail", "")
                    if status == "found":
                        st.markdown(f"- ✅ **{element}** — {detail}")
                    elif status == "missing":
                        st.markdown(f"- ❌ **{element}** — {detail}")
                    else:
                        st.markdown(f"- 🟡 **{element}** — {detail}")

            lang = st.session_state.get("creator_lang", "ko")
            summary_key = "summary_ko" if lang == "ko" else "summary_en"
            summary = cap_result.get(summary_key, cap_result.get("summary_ko", ""))
            if summary:
                st.markdown("---")
                st.markdown(f"**{t('caption_summary')}:** {summary}")

    st.divider()
    st.caption(t("contact"))

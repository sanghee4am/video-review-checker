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
    page_title="크리에이터 영상 업로드",
    page_icon="📤",
    layout="wide",
)

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
</style>
""", unsafe_allow_html=True)

# --- Hero ---
st.markdown(
    '<div class="creator-hero">'
    '<h1>영상 검수 업로드</h1>'
    '<p>영상을 업로드하면 가이드라인 준수 여부를 자동으로 검수합니다.</p>'
    '</div>',
    unsafe_allow_html=True,
)


# --- Step 1: Campaign Selection ---
st.markdown(
    '<div class="step-card">'
    '<span class="step-num">1</span>'
    '<span class="step-title">캠페인 선택</span>'
    '</div>',
    unsafe_allow_html=True,
)

campaigns = db.list_guidelines()
if not campaigns:
    st.warning("등록된 캠페인이 없습니다. 관리자에게 문의해주세요.")
    st.stop()

campaign_names = [row["campaign_name"] for row in campaigns]
selected_campaign = st.selectbox(
    "캠페인",
    campaign_names,
    key="creator_campaign_select",
    label_visibility="collapsed",
)

# Load selected guideline
selected_row = next(row for row in campaigns if row["campaign_name"] == selected_campaign)
campaign_name, guideline = db.load_guideline(selected_row["id"])

# Show brief guideline info
with st.expander("가이드라인 요약 보기", expanded=False):
    st.markdown(f"**제품:** {guideline.product_name}")
    st.markdown(f"**컨셉:** {guideline.concept}")
    st.markdown(f"**영상 길이:** {guideline.video_duration}")
    if guideline.key_message:
        st.markdown(f"**키 메시지:** {guideline.key_message}")
    if guideline.scenes:
        st.markdown(f"**장면 수:** {len(guideline.scenes)}개")
    if guideline.mandatory_elements:
        st.markdown("**필수 요소:**")
        for elem in guideline.mandatory_elements:
            st.markdown(f"  - {elem}")

# --- Step 2: Creator Info ---
st.markdown(
    '<div class="step-card">'
    '<span class="step-num">2</span>'
    '<span class="step-title">크리에이터 정보</span>'
    '</div>',
    unsafe_allow_html=True,
)

creator_name = st.text_input(
    "이름 / 채널명",
    placeholder="예: @creator_name",
    key="creator_self_name",
    label_visibility="collapsed",
)

# --- Step 3: Video Upload ---
st.markdown(
    '<div class="step-card">'
    '<span class="step-num">3</span>'
    '<span class="step-title">영상 업로드</span>'
    '</div>',
    unsafe_allow_html=True,
)

upload_method = st.radio(
    "업로드 방식",
    ["Google Drive 링크", "파일 직접 업로드"],
    horizontal=True,
    key="creator_upload_method",
)

gdrive_url = ""
video_files = None

if upload_method == "Google Drive 링크":
    gdrive_url = st.text_input(
        "Google Drive 링크",
        placeholder="https://drive.google.com/file/d/.../view 형태의 링크 붙여넣기",
        key="creator_gdrive_url",
    )
    st.caption(
        "파일이 **'링크가 있는 모든 사람'**으로 공유되어 있어야 합니다.\n"
        "Google Drive에서 파일 우클릭 → 공유 → '링크가 있는 모든 사람'으로 변경"
    )
else:
    video_files = st.file_uploader(
        "영상 파일",
        type=["mp4", "mov", "avi", "mkv"],
        accept_multiple_files=False,
        key="creator_video_upload",
        label_visibility="collapsed",
    )

# --- API Check ---
api_ok = bool(ANTHROPIC_API_KEY and OPENAI_API_KEY)
if not api_ok:
    st.error("시스템 설정 오류입니다. 관리자에게 문의해주세요.")

# --- Start Review ---
has_video = bool(gdrive_url.strip()) or bool(video_files)
has_name = bool(creator_name.strip())

if not has_name:
    st.info("이름/채널명을 입력해주세요.")
elif not has_video:
    st.info("영상 파일을 업로드하거나 Google Drive 링크를 붙여넣어주세요.")

review_btn = st.button(
    "검수 시작",
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
        st.info(f"이전 검수 이력 발견! Round {current_round}로 진행합니다.")

    progress = st.progress(0, text="준비 중...")

    try:
        # --- Download from Google Drive if needed ---
        if gdrive_url.strip() and not video_files:
            from utils.gdrive_video import download_gdrive_video, is_gdrive_url

            if not is_gdrive_url(gdrive_url.strip()):
                st.error("올바른 Google Drive 링크가 아닙니다.")
                st.stop()

            progress.progress(5, text="Google Drive에서 영상 다운로드 중...")

            def dl_progress(dl_mb, total_mb):
                if total_mb:
                    pct = min(int((dl_mb / total_mb) * 20) + 5, 25)
                    progress.progress(pct, text=f"다운로드 중... {dl_mb:.0f}/{total_mb:.0f} MB")
                else:
                    progress.progress(15, text=f"다운로드 중... {dl_mb:.0f} MB")

            filename, tmp_path = download_gdrive_video(gdrive_url.strip(), dl_progress)
            video_bytes = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)
            st.success(f"다운로드 완료: {filename} ({len(video_bytes) // (1024*1024)}MB)")
        else:
            filename = video_files.name
            video_bytes = video_files.read()

        # --- Process video ---
        progress.progress(25, text="영상 분석 중 (프레임 추출 + 음성 인식)...")
        processed_video = process_video(filename, video_bytes)

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

        progress.progress(100, text="검수 완료!")
        st.session_state["creator_report"] = report
        st.session_state["creator_processed_video"] = processed_video

    except Exception as e:
        progress.empty()
        st.error(f"오류 발생: {e}")
        import traceback
        st.code(traceback.format_exc())

# --- Display Results ---
if "creator_report" in st.session_state:
    report: ReviewReport = st.session_state["creator_report"]

    st.divider()
    st.markdown("## 검수 결과")

    # Score display
    score = report.overall_score
    score_class = "score-high" if score >= 80 else ("score-mid" if score >= 60 else "score-low")
    status_labels = {
        "approved": "승인 — 수정 없이 게시 가능합니다!",
        "revision_needed": "수정 필요 — 아래 항목을 확인해주세요.",
        "rejected": "반려 — 가이드라인을 재확인 후 다시 촬영해주세요.",
    }
    status_label = status_labels.get(report.overall_status, "확인 필요")
    status_icons = {"approved": "✅", "revision_needed": "📝", "rejected": "❌"}

    st.markdown(
        f'<div class="score-display {score_class}">{score}</div>'
        f'<div class="score-label">{status_icons.get(report.overall_status, "")} {status_label}</div>',
        unsafe_allow_html=True,
    )

    # Summary
    st.markdown(f"**요약:** {report.summary}")

    # --- Issues ---
    problem_scenes = [sr for sr in report.scene_reviews if sr.status in ("fail", "warning")]
    violated_rules = [r for r in report.rule_reviews if r.status == "violated"]

    if problem_scenes or violated_rules:
        st.markdown("### 수정이 필요한 부분")

        for sr in problem_scenes:
            icon = "❌" if sr.status == "fail" else "⚠️"
            card_class = "result-fail" if sr.status == "fail" else "result-warn"
            time_info = f" ({sr.matched_time_range})" if sr.matched_time_range else ""

            suggestion_html = ""
            if sr.suggestion:
                suggestion_html = f"<br><strong>수정 방법:</strong> {sr.suggestion}"

            st.markdown(
                f'<div class="result-card {card_class}">'
                f'<strong>{icon} Scene {sr.scene_number}{time_info}</strong><br>'
                f'<span style="color:#6b7280;font-size:13px;">가이드라인: {sr.guideline_description}</span><br>'
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
                f'<strong>수정 방법:</strong> {r.suggestion}'
                f'</div>',
                unsafe_allow_html=True,
            )

    # --- Passed items ---
    passed_scenes = [sr for sr in report.scene_reviews if sr.status == "pass"]
    if passed_scenes:
        with st.expander(f"✅ 통과 항목 ({len(passed_scenes)}개)", expanded=False):
            for sr in passed_scenes:
                st.markdown(f"- ✅ Scene {sr.scene_number}: {sr.findings[:100]}")

    # --- Revision comparison (for re-reviews) ---
    if report.revision_comparison:
        st.markdown(f"### 이전 검수 대비 변경사항 (Round {report.review_round})")

        fixed = [c for c in report.revision_comparison if c.status == "fixed"]
        partial = [c for c in report.revision_comparison if c.status == "partially_fixed"]
        pending = [c for c in report.revision_comparison if c.status == "still_pending"]

        if fixed:
            st.markdown(f"**✅ 수정 완료 ({len(fixed)}건)**")
            for c in fixed:
                st.markdown(f"- ~~{c.item}~~")

        if partial:
            st.markdown(f"**🟡 부분 수정 ({len(partial)}건)**")
            for c in partial:
                st.markdown(f"- {c.item}")

        if pending:
            st.markdown(f"**❌ 아직 미수정 ({len(pending)}건)**")
            for c in pending:
                st.markdown(f"- {c.item}")

    # --- Editing tips (simplified for creators) ---
    if report.editing_tips:
        st.markdown("### 편집 팁")
        for tip in report.editing_tips:
            scene_label = f"Scene {tip.scene_number}" if tip.scene_number > 0 else "전체"
            tip_items = tip.tip if isinstance(tip.tip, list) else [tip.tip]
            for item in tip_items:
                st.markdown(f"- **[{scene_label}]** {item}")
            if tip.font_names:
                st.caption(f"  추천 폰트: {', '.join(tip.font_names)}")

    # --- Revision items summary ---
    if report.revision_items:
        st.divider()
        st.markdown("### 수정 체크리스트")
        for i, item in enumerate(report.revision_items, 1):
            st.checkbox(item, key=f"creator_checklist_{i}")

    st.divider()
    st.caption("검수 결과에 대한 문의는 담당자에게 연락해주세요.")

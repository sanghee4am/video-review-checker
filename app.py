from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import ANTHROPIC_API_KEY, OPENAI_API_KEY, ADMIN_PASSWORD
from models.guideline import ParsedGuideline
from models.review_result import ReviewReport
import db

st.set_page_config(
    page_title="Video Guideline Checker",
    page_icon="🎬",
    layout="wide",
)

# --- Hide page navigation in sidebar (creator shouldn't navigate here) ---
st.markdown("""
<style>
    [data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# --- Admin Authentication ---
if ADMIN_PASSWORD:
    if "admin_authenticated" not in st.session_state:
        st.session_state["admin_authenticated"] = False
    if not st.session_state["admin_authenticated"]:
        st.markdown("### 🔒 어드민 로그인")
        st.caption("이 페이지는 어드민 전용입니다.")
        _pw = st.text_input("비밀번호", type="password", key="admin_pw_input")
        if st.button("로그인", use_container_width=True):
            if _pw == ADMIN_PASSWORD:
                st.session_state["admin_authenticated"] = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
        st.stop()

# --- Custom CSS ---
st.markdown("""
<style>
    /* ===== Global ===== */
    .block-container { padding-top: 1.5rem; }

    /* ===== Hero Score Card ===== */
    .hero-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 16px; padding: 28px 36px; color: #fff;
        display: flex; align-items: center; gap: 32px;
        margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    }
    .hero-score {
        font-size: 64px; font-weight: 800; line-height: 1;
        min-width: 90px; text-align: center;
    }
    .hero-score-high { color: #4ade80; }
    .hero-score-mid { color: #facc15; }
    .hero-score-low { color: #f87171; }
    .hero-info { flex: 1; }
    .hero-status {
        font-size: 20px; font-weight: 700; margin-bottom: 6px;
    }
    .hero-summary { font-size: 14px; color: #cbd5e1; line-height: 1.5; }
    .hero-stats {
        display: flex; gap: 16px; margin-top: 12px; flex-wrap: wrap;
    }
    .hero-stat {
        background: rgba(255,255,255,0.1); border-radius: 8px;
        padding: 6px 14px; font-size: 12px; color: #e2e8f0;
    }
    .hero-stat b { color: #fff; }
    .hero-filename {
        font-size: 11px; color: #64748b; margin-bottom: 4px;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }

    /* ===== Scene Cards ===== */
    .scene-card {
        border: 1px solid #e5e7eb; border-radius: 12px;
        margin-bottom: 12px; overflow: hidden;
        transition: box-shadow 0.2s;
    }
    .scene-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
    .scene-card-fail { border-left: 4px solid #ef4444; }
    .scene-card-warning { border-left: 4px solid #f59e0b; }
    .scene-card-pass { border-left: 4px solid #22c55e; }
    .scene-header {
        display: flex; align-items: center; gap: 12px;
        padding: 14px 18px; background: #fafafa;
        border-bottom: 1px solid #f0f0f0;
    }
    .scene-badge {
        display: inline-flex; align-items: center; justify-content: center;
        width: 28px; height: 28px; border-radius: 50%;
        font-size: 14px; font-weight: 700; flex-shrink: 0;
    }
    .scene-badge-pass { background: #dcfce7; color: #166534; }
    .scene-badge-fail { background: #fee2e2; color: #991b1b; }
    .scene-badge-warning { background: #fef3c7; color: #92400e; }
    .scene-title { font-weight: 600; font-size: 14px; flex: 1; }
    .scene-time { font-size: 12px; color: #9ca3af; }
    .scene-body { padding: 16px 18px; }
    .scene-body .guideline-label {
        font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
        color: #9ca3af; font-weight: 600; margin-bottom: 4px;
    }
    .scene-body .guideline-text {
        font-size: 13px; color: #6b7280; margin-bottom: 10px;
        padding-left: 12px; border-left: 2px solid #e5e7eb;
    }
    .scene-body .findings-text {
        font-size: 13px; color: #1f2937; line-height: 1.6;
        margin-bottom: 10px;
    }
    .scene-suggestion {
        background: #fff7ed; border: 1px solid #fed7aa;
        border-radius: 8px; padding: 10px 14px;
        font-size: 13px; color: #9a3412;
    }
    .scene-suggestion-label {
        font-weight: 700; font-size: 11px; text-transform: uppercase;
        letter-spacing: 0.5px; margin-bottom: 2px; color: #c2410c;
    }

    /* ===== Evidence Frames ===== */
    .evidence-frames { display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }
    .evidence-frame { display: inline-block; text-align: center; flex-shrink: 0; }
    .evidence-frame img {
        width: 110px; height: auto; border-radius: 6px;
        border: 2px solid #e0e0e0; object-fit: cover;
    }
    .evidence-frame .ef-time { font-size: 10px; color: #888; margin-top: 2px; }
    .evidence-frame-fail img { border-color: #ef4444; }
    .evidence-frame-warning img { border-color: #f59e0b; }
    .evidence-frame-pass img { border-color: #22c55e; }

    /* ===== Rule Cards ===== */
    .rule-card {
        border-radius: 10px; padding: 14px 18px;
        margin-bottom: 8px; font-size: 13px; line-height: 1.6;
    }
    .rule-violated {
        background: #fef2f2; border: 1px solid #fecaca;
        border-left: 4px solid #ef4444;
    }
    .rule-unclear {
        background: #fffbeb; border: 1px solid #fde68a;
        border-left: 4px solid #f59e0b;
    }
    .rule-cat {
        display: inline-block; background: rgba(0,0,0,0.06);
        border-radius: 4px; padding: 1px 8px; font-size: 11px;
        font-weight: 600; text-transform: uppercase; margin-right: 6px;
    }
    .rule-desc { font-weight: 600; color: #1f2937; }
    .rule-evidence { color: #6b7280; margin-top: 4px; }
    .rule-suggestion { color: #b45309; font-weight: 500; margin-top: 4px; }

    /* ===== Mandatory Grid ===== */
    .mandatory-grid { display: flex; flex-wrap: wrap; gap: 8px; }
    .mandatory-item {
        display: inline-flex; align-items: center; gap: 6px;
        background: #f8fafc; border: 1px solid #e2e8f0;
        border-radius: 8px; padding: 8px 14px; font-size: 13px;
    }
    .mandatory-item-fail { border-color: #fecaca; background: #fef2f2; }

    /* ===== Manual Review ===== */
    .manual-flag {
        background: #fffbeb; border: 1px solid #fde68a;
        border-radius: 8px; padding: 12px 16px;
        margin-bottom: 8px; font-size: 13px;
    }

    /* ===== Batch Summary Cards ===== */
    .batch-card {
        background: #f8fafc; border-radius: 12px; padding: 16px;
        text-align: center; border: 2px solid transparent;
        cursor: default; transition: all 0.15s;
    }
    .batch-card-selected { border-color: #3b82f6; background: #eff6ff; }
    .batch-card .bc-name {
        font-size: 11px; color: #64748b;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        margin-bottom: 4px;
    }
    .batch-card .bc-score { font-size: 32px; font-weight: 800; line-height: 1.2; }
    .batch-card .bc-status { font-size: 12px; color: #64748b; margin-top: 2px; }

    /* ===== Editing Tips Table ===== */
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

    /* ===== Upload Check ===== */
    .upload-result { margin: 8px 0; }
    .upload-found { color: #16a34a; }
    .upload-missing { color: #dc2626; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

st.title("🎬 영상 가이드라인 검수 자동화")
st.caption("크리에이터 영상이 가이드라인에 부합하는지 AI로 1차 검수합니다.")

# --- Sidebar: File Uploads (step-by-step) ---
with st.sidebar:
    # Workflow progress indicator
    _has_gl = "parsed_guideline" in st.session_state
    _has_result = "review_report" in st.session_state
    _step1_icon = "✅" if _has_gl else "👉"
    _step2_icon = "✅" if _has_result else ("👉" if _has_gl else "⬜")

    st.markdown(
        f"**{_step1_icon} STEP 1** 가이드라인 준비 → "
        f"**{_step2_icon} STEP 2** 영상 검수"
    )
    st.divider()

    st.subheader(f"{_step1_icon} 1. 가이드라인")

    # Saved guidelines loader
    saved_list = db.list_guidelines()
    if saved_list:
        saved_names = ["— 새로 업로드 —"] + [row["campaign_name"] for row in saved_list]
        saved_selection = st.selectbox(
            "저장된 가이드라인",
            saved_names,
            key="saved_guideline_select",
        )
        if saved_selection != "— 새로 업로드 —":
            match_row = next((row for row in saved_list if row["campaign_name"] == saved_selection), None)
            if match_row:
                load_btn = st.button("📂 불러오기", key="load_saved_gl", use_container_width=True)
                if load_btn:
                    camp_name, loaded_gl = db.load_guideline(match_row["id"])
                    st.session_state["parsed_guideline"] = loaded_gl
                    st.session_state["guideline_images"] = []
                    st.success(f"'{camp_name}' 가이드라인 불러옴!")
                    st.rerun()

                # Delete button
                del_btn = st.button("🗑️ 삭제", key="delete_saved_gl", use_container_width=True)
                if del_btn:
                    db.delete_guideline(match_row["id"])
                    st.success(f"'{saved_selection}' 삭제됨")
                    st.rerun()

        st.divider()

    guideline_input_mode = st.radio(
        "입력 방식",
        ["파일 업로드", "URL 링크"],
        horizontal=True,
        key="guideline_input_mode",
    )

    guideline_files = None
    guideline_url = None

    if guideline_input_mode == "파일 업로드":
        guideline_files = st.file_uploader(
            "PDF, Excel, 이미지 파일 업로드",
            type=["pdf", "xlsx", "xls", "png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="guideline_upload",
        )
    else:
        guideline_url = st.text_input(
            "가이드라인 URL",
            placeholder="Google Drive, Sheets, Slides 링크 붙여넣기",
            key="guideline_url",
        )
        st.caption("지원: Google Drive, Sheets, Slides (공개 링크)")

    # URL fetch button + result storage
    url_fetch_btn = False
    if guideline_input_mode == "URL 링크" and guideline_url:
        url_fetch_btn = st.button("📥 URL에서 가져오기", use_container_width=True)

    if url_fetch_btn and guideline_url:
        with st.spinner("URL에서 가이드라인을 가져오는 중..."):
            from processors.url_fetcher import fetch_from_url
            try:
                filename, file_bytes = fetch_from_url(guideline_url)
                st.session_state["url_fetched_files"] = [(filename, file_bytes)]
                st.success(f"가져오기 완료: {filename} ({len(file_bytes) // 1024}KB)")
            except ValueError as e:
                st.error(str(e))
                st.session_state.pop("url_fetched_files", None)

    if not _has_gl:
        st.info("👆 가이드라인을 먼저 파싱하세요. 이후 영상 검수 단계가 열립니다.")

    # --- Steps 2~4: only visible after guideline is parsed ---
    video_files = None
    gdrive_video_url = ""
    creator_name = ""
    review_memo = ""
    has_video_input = False

    if _has_gl:
        st.subheader(f"{_step2_icon} 2. 크리에이터 영상")
        video_input_mode = st.radio(
            "영상 입력 방식",
            ["파일 업로드", "Google Drive 링크"],
            horizontal=True,
            key="video_input_mode",
        )

        if video_input_mode == "파일 업로드":
            video_files = st.file_uploader(
                "영상 파일 업로드 (여러 개 가능)",
                type=["mp4", "mov", "avi", "mkv"],
                accept_multiple_files=True,
                key="video_upload",
            )
        else:
            gdrive_video_url = st.text_input(
                "Google Drive 영상 링크",
                placeholder="https://drive.google.com/file/d/.../view",
                key="gdrive_video_url",
            )
            st.caption("파일이 '링크가 있는 모든 사람'으로 공유되어 있어야 합니다.")

        st.subheader("3. 크리에이터 정보")
        creator_name = st.text_input(
            "크리에이터 이름/채널명",
            placeholder="예: @creator_name",
            key="creator_name",
        )
        st.caption("이전 검수 이력과 비교하려면 동일한 이름을 사용하세요.")

        # Show previous review info if available
        if creator_name:
            g = st.session_state["parsed_guideline"]
            campaign_id = g.title or g.product_name or "default"
            prev = db.get_previous_review(campaign_id, creator_name)
            if prev:
                prev_report, prev_round = prev
                st.info(
                    f"📋 이전 검수 이력 발견! (Round {prev_round}, "
                    f"점수: {prev_report.overall_score}점, "
                    f"상태: {prev_report.overall_status})\n"
                    f"→ 이번 검수는 **Round {prev_round + 1}**로 진행됩니다."
                )

        st.subheader("4. 메모 (선택)")
        review_memo = st.text_area(
            "가이드라인 보충/수정 사항",
            placeholder="예: CTA 문구는 말하지 않아도 됨\n예: B&A는 선택사항으로 변경됨",
            height=100,
            key="review_memo",
        )
        st.caption("가이드라인과 달라진 내용이나 추가 참고사항을 입력하세요.")

    st.divider()

    # API key check
    api_ok = True
    if not ANTHROPIC_API_KEY:
        st.error("ANTHROPIC_API_KEY가 .env에 설정되지 않았습니다.")
        api_ok = False
    if not OPENAI_API_KEY:
        st.error("OPENAI_API_KEY가 .env에 설정되지 않았습니다.")
        api_ok = False

    has_guideline_input = bool(guideline_files) or ("url_fetched_files" in st.session_state)

    if not _has_gl:
        # Step 1: only show parse button
        parse_btn = st.button(
            "📋 가이드라인 파싱",
            disabled=not (has_guideline_input and api_ok),
            use_container_width=True,
            type="primary",
        )
        review_btn = False
    else:
        # Step 2: show both buttons
        parse_btn = st.button(
            "📋 가이드라인 다시 파싱",
            disabled=not (has_guideline_input and api_ok),
            use_container_width=True,
        )
        has_video_input = bool(video_files) or bool(gdrive_video_url.strip())
        review_btn = st.button(
            "🔍 검수 시작",
            disabled=not (
                has_video_input
                and api_ok
            ),
            use_container_width=True,
            type="primary",
        )

# --- Main Area ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 가이드라인", "🔍 검수 결과", "🎨 편집 팁",
    "📊 브랜드사 전달", "🔗 업로드 확인",
])

# ===== Guideline Parsing =====
if parse_btn and has_guideline_input:
    with st.spinner("가이드라인을 분석하고 있습니다..."):
        from processors.guideline_parser import parse_guideline

        # Collect files from upload or URL fetch
        if guideline_files:
            files = [(f.name, f.read()) for f in guideline_files]
            for f in guideline_files:
                f.seek(0)
        else:
            files = st.session_state.get("url_fetched_files", [])

        try:
            guideline, guideline_images = parse_guideline(files)
            st.session_state["parsed_guideline"] = guideline
            st.session_state["guideline_images"] = guideline_images
            st.session_state["show_save_guideline"] = True
            st.success("가이드라인 파싱 완료!")
        except Exception as e:
            st.error(f"가이드라인 파싱 오류: {e}")

# Display parsed guideline
with tab1:
    if "parsed_guideline" in st.session_state:
        g: ParsedGuideline = st.session_state["parsed_guideline"]

        # Header info
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"### {g.title}")
            st.markdown(f"**제품:** {g.product_name}")
            st.markdown(f"**컨셉:** {g.concept}")
        with col2:
            st.markdown(f"**영상 길이:** {g.video_duration}")
            st.markdown(f"**키 메시지:** {g.key_message}")
            if g.content_objective:
                st.markdown(f"**목표:** {g.content_objective}")

        st.divider()

        # Rules
        if g.rules:
            st.subheader("📌 규칙 (Do / Don't / Brand Rules)")
            rule_cols = st.columns(3)

            dos = [r for r in g.rules if r.category == "do"]
            donts = [r for r in g.rules if r.category in ("dont", "brand_rule")]
            mandatories = [r for r in g.rules if r.category == "mandatory"]

            with rule_cols[0]:
                st.markdown("**✅ DO**")
                for r in dos:
                    st.markdown(f"- {r.description}")

            with rule_cols[1]:
                st.markdown("**❌ DON'T / Brand Rules**")
                for r in donts:
                    severity_icon = "🚨" if r.severity == "strict" else "⚠️"
                    st.markdown(f"- {severity_icon} {r.description}")

            with rule_cols[2]:
                st.markdown("**📎 MANDATORY**")
                for r in mandatories:
                    st.markdown(f"- {r.description}")

        st.divider()

        # Scenes
        if g.scenes:
            st.subheader("🎬 장면별 가이드")
            for scene in g.scenes:
                with st.expander(
                    f"Scene {scene.scene_number}"
                    + (f" ({scene.time_range})" if scene.time_range else ""),
                    expanded=False,
                ):
                    st.markdown(f"**촬영 지시:** {scene.description}")
                    if scene.visual_direction:
                        st.markdown(f"**시각적 연출:** {scene.visual_direction}")
                    if scene.script_suggestion:
                        st.markdown(f"**스크립트 제안:** _{scene.script_suggestion}_")
                    if scene.text_overlay:
                        st.markdown(f"**텍스트 오버레이:** `{scene.text_overlay}`")

        # Mandatory elements
        if g.mandatory_elements:
            st.divider()
            st.subheader("📎 필수 포함 요소")
            for elem in g.mandatory_elements:
                st.markdown(f"- {elem}")

        # Flow
        if g.recommended_flow:
            st.divider()
            st.subheader("🔄 권장 흐름")
            st.info(g.recommended_flow)
        # --- Save guideline ---
        if st.session_state.get("show_save_guideline"):
            st.divider()
            save_col1, save_col2 = st.columns([3, 1])
            with save_col1:
                campaign_name = st.text_input(
                    "캠페인 이름",
                    value=g.title or g.product_name or "",
                    placeholder="예: 2024 봄 신제품 캠페인",
                    key="save_campaign_name",
                )
            with save_col2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 가이드라인 저장", use_container_width=True, key="save_gl_btn"):
                    if campaign_name.strip():
                        db.save_guideline(campaign_name.strip(), g)
                        st.session_state["show_save_guideline"] = False
                        st.success(f"'{campaign_name}' 저장 완료! 사이드바에서 불러올 수 있습니다.")
                        st.rerun()
                    else:
                        st.warning("캠페인 이름을 입력해주세요.")

        # --- Creator Link Generator ---
        st.divider()
        st.subheader("🔗 크리에이터 전용 링크 생성")
        st.caption("크리에이터 이름을 입력하면 검수 업로드 전용 링크가 생성됩니다. 링크를 받은 크리에이터는 영상만 올리면 됩니다.")

        saved_campaign_name = g.title or g.product_name or ""
        # Check if this guideline is saved
        saved_gl = db.load_guideline_by_name(saved_campaign_name) if saved_campaign_name else None
        if not saved_gl:
            # Try with any saved guidelines
            all_saved = db.list_guidelines()
            if all_saved:
                link_campaign = st.selectbox(
                    "캠페인 선택",
                    [row["campaign_name"] for row in all_saved],
                    key="link_campaign_select",
                )
            else:
                st.info("먼저 가이드라인을 저장해주세요.")
                link_campaign = None
        else:
            link_campaign = saved_campaign_name

        if link_campaign:
            creator_input = st.text_area(
                "크리에이터 목록",
                placeholder="한 줄에 하나씩 입력\n예:\n@beauty_creator\n@food_lover\n@tech_review",
                height=120,
                key="link_creator_list",
            )

            if st.button("🔗 링크 생성", use_container_width=True, key="generate_links_btn"):
                creators = [c.strip() for c in creator_input.strip().split("\n") if c.strip()]
                if creators:
                    from urllib.parse import quote
                    base_url = "https://video-review-checker-2f6utmtejjnlbpi3xy5tsq.streamlit.app/Creator_Upload"

                    link_lines = []
                    for c in creators:
                        url = f"{base_url}?campaign={quote(link_campaign)}&creator={quote(c)}"
                        link_lines.append(f"{c}\n{url}\n")

                    links_text = "\n".join(link_lines)
                    st.code(links_text, language=None)
                    st.caption("위 내용을 복사해서 각 크리에이터에게 전달해주세요.")
                else:
                    st.warning("크리에이터 이름을 입력해주세요.")

            # --- Creator Submission Status ---
            st.divider()
            # --- Campaign Overview (all campaigns summary) ---
            all_campaigns_summary = db.get_campaigns_summary()
            if all_campaigns_summary and len(all_campaigns_summary) > 1:
                st.subheader("🗂️ 전체 캠페인 현황")
                overview_cols = st.columns(min(len(all_campaigns_summary), 4))
                for i, cs in enumerate(all_campaigns_summary):
                    col = overview_cols[i % len(overview_cols)]
                    total = cs["total_creators"]
                    pct = round(cs["approved"] / total * 100) if total else 0
                    col.markdown(
                        f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;'
                        f'padding:16px;margin-bottom:8px;">'
                        f'<div style="font-weight:700;font-size:14px;margin-bottom:8px;">{cs["campaign_name"]}</div>'
                        f'<div style="font-size:12px;color:#64748b;">'
                        f'크리에이터 <b>{total}</b>명 · 평균 <b>{cs["avg_score"]}</b>점<br>'
                        f'✅{cs["approved"]} 📝{cs["revision_needed"]} ❌{cs["rejected"]}'
                        f' · 캡션완료 {cs["caption_done"]}/{total}<br>'
                        f'<div style="background:#e2e8f0;border-radius:4px;height:6px;margin-top:6px;">'
                        f'<div style="background:#22c55e;border-radius:4px;height:6px;width:{pct}%;"></div>'
                        f'</div>'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )
                st.divider()

            st.subheader("📊 크리에이터 제출 현황")
            campaign_id_for_status = g.title or g.product_name or link_campaign
            submissions = db.get_submission_status(campaign_id_for_status)
            if submissions:
                status_icons = {"approved": "✅", "revision_needed": "📝", "rejected": "❌"}
                score_icons = lambda s: "🟢" if s >= 80 else ("🟡" if s >= 60 else "🔴")
                decision_labels = {
                    "approved": "✅수동승인",
                    "auto_approved": "🤖자동승인",
                    "rejected": "❌수동반려",
                    "revision_needed": "📝수동수정요청",
                }

                for idx, sub in enumerate(submissions):
                    sc = sub.get("overall_score", 0)
                    st_icon = status_icons.get(sub.get("overall_status", ""), "❓")
                    ts = sub["created_at"][:16].replace("T", " ") if sub.get("created_at") else ""

                    # Badges from vc_reviews columns
                    extra_badges = ""
                    if sub.get("admin_decision"):
                        extra_badges += f" | {decision_labels.get(sub['admin_decision'], sub['admin_decision'])}"
                    if sub.get("brand_feedback"):
                        extra_badges += " | 💬피드백"
                    # Caption check status
                    cap = sub.get("caption_check_result")
                    if cap:
                        cap_ok = cap.get("all_passed", False) if isinstance(cap, dict) else False
                        extra_badges += " | 🔗캡션✅" if cap_ok else " | 🔗캡션❌"

                    col_info, col_btn = st.columns([5, 1])
                    with col_info:
                        st.markdown(
                            f"{score_icons(sc)} **{sub['creator_name']}** — "
                            f"Round {sub['round']} | 점수: {sc} {st_icon} | {ts}"
                            f"{extra_badges}"
                        )
                    with col_btn:
                        if st.button("상세", key=f"detail_{idx}"):
                            st.session_state["view_creator_detail"] = sub["creator_name"]

                # Show detailed review history for selected creator
                if "view_creator_detail" in st.session_state:
                    detail_creator = st.session_state["view_creator_detail"]
                    st.markdown(f"---\n#### 📝 {detail_creator} 검수 이력")
                    reviews = db.get_creator_reviews(campaign_id_for_status, detail_creator)
                    for rev in reviews:
                        r_sc = rev.get("overall_score", 0)
                        r_status = status_icons.get(rev.get("overall_status", ""), "❓")
                        r_ts = rev["created_at"][:16].replace("T", " ") if rev.get("created_at") else ""

                        md = rev.get("admin_decision")
                        md_badge = f" — {decision_labels.get(md, md)}" if md else ""

                        with st.expander(
                            f"Round {rev.get('round', 1)} — {r_sc}점 {r_status}{md_badge} ({r_ts})",
                            expanded=(rev == reviews[0]),
                        ):
                            report = ReviewReport.model_validate(rev["report_json"])
                            st.markdown(f"**요약:** {report.summary}")

                            if md:
                                st.info(
                                    f"**수동 결정:** {decision_labels.get(md, md)}"
                                    + (f"\n메모: {rev['admin_memo']}" if rev.get("admin_memo") else "")
                                )
                            if rev.get("brand_feedback"):
                                st.warning(f"**브랜드 피드백:** {rev['brand_feedback']}")

                            if report.revision_items:
                                st.markdown("**수정 필요 항목:**")
                                for item in report.revision_items:
                                    st.markdown(f"- {item}")
                            if report.manual_review_flags:
                                st.markdown("**수동 검토 필요:**")
                                for flag in report.manual_review_flags:
                                    st.markdown(f"- ⚠️ {flag}")

                            # --- Admin decision buttons on every review ---
                            rev_id = rev["id"]
                            if not md or md == "auto_approved":
                                st.markdown("**어드민 수동 결정:**")
                                d_memo = st.text_input(
                                    "메모 (선택)",
                                    placeholder="판단 근거 입력",
                                    key=f"dmemo_{rev_id}",
                                )
                                dc1, dc2, dc3 = st.columns(3)
                                with dc1:
                                    if st.button("✅ 승인", key=f"dappr_{rev_id}", use_container_width=True):
                                        db.save_admin_decision(rev_id, "approved", d_memo)
                                        st.rerun()
                                with dc2:
                                    if st.button("📝 수정요청", key=f"drev_{rev_id}", use_container_width=True):
                                        db.save_admin_decision(rev_id, "revision_needed", d_memo)
                                        st.rerun()
                                with dc3:
                                    if st.button("❌ 반려", key=f"drej_{rev_id}", use_container_width=True):
                                        db.save_admin_decision(rev_id, "rejected", d_memo)
                                        st.rerun()

                            if report.email_draft:
                                st.text_area(
                                    "이메일 초안",
                                    report.email_draft,
                                    height=120,
                                    key=f"email_draft_{rev_id}",
                                )

                    if st.button("✕ 닫기", key="close_detail"):
                        del st.session_state["view_creator_detail"]
                        st.rerun()

            else:
                st.caption("아직 제출한 크리에이터가 없습니다.")

    else:
        st.info("👈 사이드바에서 가이드라인 파일을 업로드하고 '가이드라인 파싱' 버튼을 눌러주세요.")

# ===== Video Review (multi-video batch) =====
if review_btn and has_video_input and "parsed_guideline" in st.session_state:
    from processors.video_processor import process_video, process_videos_parallel
    from analyzer.compliance_checker import run_compliance_check

    guideline = st.session_state["parsed_guideline"]
    guideline_images = st.session_state.get("guideline_images", [])
    c_name = st.session_state.get("creator_name", "").strip()
    campaign_id = guideline.title or guideline.product_name or "default"

    # Get previous review for comparison
    previous_report = None
    current_round = 1
    if c_name:
        prev = db.get_previous_review(campaign_id, c_name)
        if prev:
            previous_report, prev_round = prev
            current_round = prev_round + 1

    progress_bar = st.progress(0, text="처리 준비 중...")

    try:
        # --- Download from Google Drive if needed ---
        video_items = []
        if gdrive_video_url.strip() and not video_files:
            from utils.gdrive_video import download_gdrive_video, is_gdrive_url

            if not is_gdrive_url(gdrive_video_url.strip()):
                st.error("올바른 Google Drive 링크가 아닙니다.")
                st.stop()

            progress_bar.progress(3, text="Google Drive에서 영상 다운로드 중...")

            def dl_progress(dl_mb, total_mb):
                if total_mb:
                    pct = min(int((dl_mb / total_mb) * 15) + 3, 18)
                    progress_bar.progress(pct, text=f"다운로드 중... {dl_mb:.0f}/{total_mb:.0f} MB")
                else:
                    progress_bar.progress(10, text=f"다운로드 중... {dl_mb:.0f} MB")

            filename, tmp_path = download_gdrive_video(gdrive_video_url.strip(), dl_progress)
            video_bytes = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)
            video_items.append((filename, video_bytes))
            st.success(f"다운로드 완료: {filename} ({len(video_bytes) // (1024*1024)}MB)")
        else:
            for vf in video_files:
                video_items.append((vf.name, vf.read()))

        num_videos = len(video_items)

        # --- Phase 1: Parallel preprocessing (ffmpeg + Whisper) ---
        progress_bar.progress(5, text=f"영상 {num_videos}개 병렬 전처리 중 (프레임 추출 + STT)...")

        def preprocess_progress(done, total, fname):
            pct = 5 + int((done / total) * 25)
            progress_bar.progress(pct, text=f"전처리 완료: {done}/{total} ({fname})")

        processed_videos = process_videos_parallel(
            video_items,
            max_workers=4,
            progress_callback=preprocess_progress,
        )

        # --- Phase 2: Sequential compliance checks (Claude API) ---
        all_results = {}  # filename -> {"processed_video": ..., "report": ...}
        memo = st.session_state.get("review_memo", "")

        for vid_idx, (filename, processed_video) in enumerate(processed_videos.items()):
            base_pct = 30 + int((vid_idx / num_videos) * 65)
            per_video_pct = int(65 / num_videos)

            progress_bar.progress(
                base_pct,
                text=f"검수 중: {vid_idx + 1}/{num_videos} — {filename}",
            )

            def update_progress(step, total, msg):
                pct = base_pct + int((step / total) * per_video_pct)
                progress_bar.progress(min(pct, 95), text=f"[{filename}] {msg}")

            report = run_compliance_check(
                guideline=guideline,
                guideline_images=guideline_images,
                video=processed_video,
                progress_callback=update_progress,
                memo=memo,
                previous_report=previous_report,
                review_round=current_round,
            )

            all_results[filename] = {
                "processed_video": processed_video,
                "report": report,
            }

        st.session_state["batch_results"] = all_results
        first_key = next(iter(all_results))
        st.session_state["processed_video"] = all_results[first_key]["processed_video"]
        st.session_state["review_report"] = all_results[first_key]["report"]
        st.session_state["selected_video"] = first_key

        # Save review history
        if c_name:
            for fname, data in all_results.items():
                rid = db.save_review(campaign_id, c_name, data["report"], current_round)
                st.session_state["last_review_id"] = rid
                st.session_state["last_review_campaign"] = campaign_id
                st.session_state["last_review_creator"] = c_name

        progress_bar.progress(100, text=f"검수 완료! ({num_videos}개 영상)")
        round_msg = f" (Round {current_round})" if current_round > 1 else ""
        st.success(f"검수가 완료되었습니다!{round_msg} {num_videos}개 영상의 결과를 '검수 결과' 탭에서 확인하세요.")

    except Exception as e:
        progress_bar.empty()
        st.error(f"검수 오류: {e}")
        import traceback
        st.code(traceback.format_exc())


# --- Helper functions ---
def _extract_timestamps(text: str) -> list[float]:
    import re as _re2
    return [float(m) for m in _re2.findall(r"\[(\d+(?:\.\d+)?)초\]", text)]


def _get_frame_at(timestamp: float, processed_video) -> str | None:
    import base64 as _b642
    if not processed_video or not processed_video.frames:
        return None
    best = min(processed_video.frames, key=lambda f: abs(f.timestamp - timestamp))
    if abs(best.timestamp - timestamp) > 5.0:
        return None
    return _b642.b64encode(best.image_bytes).decode("utf-8")


def _build_evidence_frames_html(
    timestamps: list[float], processed_video, status: str = ""
) -> str:
    if not timestamps or not processed_video:
        return ""
    frame_class = f"evidence-frame-{status}" if status else "evidence-frame"
    parts = []
    seen = set()
    for ts in timestamps[:4]:
        rounded = round(ts, 1)
        if rounded in seen:
            continue
        seen.add(rounded)
        b64 = _get_frame_at(ts, processed_video)
        if b64:
            parts.append(
                f'<div class="evidence-frame {frame_class}">'
                f'<img src="data:image/jpeg;base64,{b64}" />'
                f'<div class="ef-time">{rounded}초</div>'
                f'</div>'
            )
    if not parts:
        return ""
    return f'<div class="evidence-frames">{"".join(parts)}</div>'


def _get_scene_frames_html(time_range: str, processed_video, status: str = "") -> str:
    import re as _re3
    m = _re3.search(r"([\d.]+)\s*[-~]\s*([\d.]+)", time_range or "")
    if not m:
        return ""
    t_start, t_end = float(m.group(1)), float(m.group(2))
    timestamps = [t_start]
    if t_end - t_start > 2:
        timestamps.append((t_start + t_end) / 2)
    if t_end - t_start > 1:
        timestamps.append(t_end)
    return _build_evidence_frames_html(timestamps, processed_video, status)


# ===== Tab 2: Review Results (main dashboard) =====
with tab2:
    if "review_report" in st.session_state:
        report: ReviewReport = st.session_state["review_report"]
        _pv = st.session_state.get("processed_video")

        # --- Batch video selector (if multiple) ---
        if "batch_results" in st.session_state and len(st.session_state["batch_results"]) > 1:
            batch_results = st.session_state["batch_results"]
            video_names = list(batch_results.keys())

            # Batch summary cards
            cols = st.columns(min(len(video_names), 5))
            for i, vname in enumerate(video_names):
                r = batch_results[vname]["report"]
                col = cols[i % len(cols)]
                score = r.overall_score
                color = "#22c55e" if score >= 80 else ("#f59e0b" if score >= 60 else "#ef4444")
                status_icon = {"approved": "✅", "revision_needed": "📝", "rejected": "❌"}.get(r.overall_status, "❓")
                is_sel = "batch-card-selected" if vname == st.session_state.get("selected_video") else ""
                col.markdown(
                    f'<div class="batch-card {is_sel}">'
                    f'<div class="bc-name">{vname}</div>'
                    f'<div class="bc-score" style="color:{color};">{score}</div>'
                    f'<div class="bc-status">{status_icon} {r.overall_status.replace("_", " ")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            selected = st.selectbox(
                "영상 선택",
                video_names,
                index=video_names.index(st.session_state.get("selected_video", video_names[0])),
                key="video_selector",
                label_visibility="collapsed",
            )
            if selected != st.session_state.get("selected_video"):
                st.session_state["selected_video"] = selected
                st.session_state["review_report"] = batch_results[selected]["report"]
                st.session_state["processed_video"] = batch_results[selected]["processed_video"]
                st.rerun()

        # --- Hero Score Card ---
        score = report.overall_score
        score_class = "hero-score-high" if score >= 90 else ("hero-score-mid" if score >= 60 else "hero-score-low")

        # 90점 미만이면 AI가 approved라 해도 revision_needed로 강제
        _display_status = report.overall_status
        if score < 90 and _display_status == "approved":
            _display_status = "revision_needed"

        status_labels = {
            "approved": "✅ 승인 — 수정 없이 게시 가능",
            "revision_needed": "📝 수정 필요 — 아래 항목 확인 후 재촬영/편집",
            "rejected": "❌ 반려 — 가이드라인 재확인 필요",
        }
        status_label = status_labels.get(_display_status, "❓ 미정")

        # Stats
        s_pass = sum(1 for s in report.scene_reviews if s.status == "pass")
        s_fail = sum(1 for s in report.scene_reviews if s.status == "fail")
        s_warn = sum(1 for s in report.scene_reviews if s.status == "warning")
        n_violated = sum(1 for r in report.rule_reviews if r.status == "violated")
        n_manual = len(report.manual_review_flags)

        fname_html = ""
        if st.session_state.get("selected_video"):
            fname_html = f'<div class="hero-filename">📁 {st.session_state["selected_video"]}</div>'

        st.markdown(
            f'<div class="hero-card">'
            f'<div class="hero-score {score_class}">{score}</div>'
            f'<div class="hero-info">'
            f'{fname_html}'
            f'<div class="hero-status">{status_label}</div>'
            f'<div class="hero-summary">{report.summary}</div>'
            f'<div class="hero-stats">'
            f'<div class="hero-stat">장면 <b>✅{s_pass}</b> ❌{s_fail} ⚠️{s_warn}</div>'
            f'<div class="hero-stat">규칙 위반 <b>{n_violated}건</b></div>'
            f'<div class="hero-stat">수동 확인 <b>{n_manual}건</b></div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )

        # --- Issues first: violations + manual flags ---
        has_issues = (n_violated > 0 or s_fail > 0 or s_warn > 0 or n_manual > 0)

        if has_issues:
            st.markdown("### 🚨 수정 필요 항목")

            # Failed/warning scenes first
            problem_scenes = [sr for sr in report.scene_reviews if sr.status in ("fail", "warning")]
            if problem_scenes:
                for sr in problem_scenes:
                    status = sr.status
                    icon = "❌" if status == "fail" else "⚠️"
                    badge_class = f"scene-badge-{status}"
                    card_class = f"scene-card-{status}"

                    frames_html = _get_scene_frames_html(sr.matched_time_range, _pv, status)
                    finding_ts = _extract_timestamps(sr.findings)
                    finding_frames = _build_evidence_frames_html(finding_ts, _pv, status)

                    suggestion_html = ""
                    if sr.suggestion:
                        suggestion_html = (
                            f'<div class="scene-suggestion">'
                            f'<div class="scene-suggestion-label">수정 제안</div>'
                            f'{sr.suggestion}</div>'
                        )

                    st.markdown(
                        f'<div class="scene-card {card_class}">'
                        f'<div class="scene-header">'
                        f'<div class="scene-badge {badge_class}">{icon}</div>'
                        f'<div class="scene-title">Scene {sr.scene_number}</div>'
                        f'<div class="scene-time">{sr.matched_time_range or ""}</div>'
                        f'</div>'
                        f'<div class="scene-body">'
                        f'{frames_html}'
                        f'<div class="guideline-label">가이드라인 요구사항</div>'
                        f'<div class="guideline-text">{sr.guideline_description}</div>'
                        f'<div class="findings-text">{sr.findings}</div>'
                        f'{finding_frames if finding_frames != frames_html else ""}'
                        f'{suggestion_html}'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )

            # Rule violations
            violated = [r for r in report.rule_reviews if r.status == "violated"]
            if violated:
                st.markdown("#### 규칙 위반")
                for r in violated:
                    evidence_ts = _extract_timestamps(r.evidence)
                    evidence_html = _build_evidence_frames_html(evidence_ts, _pv, "fail")
                    st.markdown(
                        f'<div class="rule-card rule-violated">'
                        f'<span class="rule-cat">{r.rule_category}</span>'
                        f'<span class="rule-desc">{r.rule_description}</span>'
                        f'<div class="rule-evidence">근거: {r.evidence}</div>'
                        f'{evidence_html}'
                        f'<div class="rule-suggestion">💡 {r.suggestion}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # Unclear rules
            unclear = [r for r in report.rule_reviews if r.status == "unclear"]
            if unclear:
                st.markdown("#### 확인 필요 규칙")
                for r in unclear:
                    evidence_ts = _extract_timestamps(r.evidence)
                    evidence_html = _build_evidence_frames_html(evidence_ts, _pv, "warning")
                    st.markdown(
                        f'<div class="rule-card rule-unclear">'
                        f'<span class="rule-cat">{r.rule_category}</span>'
                        f'<span class="rule-desc">{r.rule_description}</span>'
                        f'<div class="rule-evidence">{r.evidence}</div>'
                        f'{evidence_html}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # Manual review flags
            if report.manual_review_flags:
                st.markdown("#### 👁️ 수동 확인 필요")
                for flag in report.manual_review_flags:
                    flag_ts = _extract_timestamps(flag)
                    flag_frames = _build_evidence_frames_html(flag_ts, _pv, "warning")
                    st.markdown(
                        f'<div class="manual-flag">🔍 {flag}{flag_frames}</div>',
                        unsafe_allow_html=True,
                    )

                # --- Admin Manual Decision (works with session review or from dashboard) ---
                _rid = st.session_state.get("last_review_id")
                if _rid:
                    st.markdown("**어드민 수동 결정:**")
                    manual_memo = st.text_input(
                        "메모 (선택)",
                        placeholder="수동 확인 후 판단 근거를 입력하세요",
                        key="manual_decision_memo",
                    )
                    col_approve, col_revision, col_reject = st.columns(3)
                    with col_approve:
                        if st.button("✅ 승인", key="manual_approve", use_container_width=True):
                            db.save_admin_decision(_rid, "approved", manual_memo)
                            st.success("✅ 승인 처리되었습니다.")
                            st.rerun()
                    with col_revision:
                        if st.button("📝 수정 필요", key="manual_revision", use_container_width=True):
                            db.save_admin_decision(_rid, "revision_needed", manual_memo)
                            st.warning("📝 수정 필요로 처리되었습니다.")
                            st.rerun()
                    with col_reject:
                        if st.button("❌ 반려", key="manual_reject", use_container_width=True, type="primary"):
                            db.save_admin_decision(_rid, "rejected", manual_memo)
                            st.error("❌ 반려 처리되었습니다.")
                            st.rerun()
                else:
                    st.caption("💡 가이드라인 탭의 '제출 현황 → 상세'에서도 수동 결정이 가능합니다.")

            # --- Revision Comparison (re-review) ---
            if report.revision_comparison:
                st.markdown("### 🔄 이전 검수 대비 변경사항")
                st.markdown(f"**Review Round {report.review_round}**")

                comp_fixed = [c for c in report.revision_comparison if c.status == "fixed"]
                comp_partial = [c for c in report.revision_comparison if c.status == "partially_fixed"]
                comp_pending = [c for c in report.revision_comparison if c.status == "still_pending"]

                if comp_fixed:
                    st.markdown(f"**✅ 수정 완료 ({len(comp_fixed)}건)**")
                    for c in comp_fixed:
                        st.markdown(f"- ✅ ~~{c.item}~~")

                if comp_partial:
                    st.markdown(f"**🟡 부분 수정 ({len(comp_partial)}건)**")
                    for c in comp_partial:
                        st.markdown(f"- 🟡 {c.item}")
                        if c.current_finding:
                            st.caption(f"   현재: {c.current_finding[:100]}")

                if comp_pending:
                    st.markdown(f"**❌ 아직 미수정 ({len(comp_pending)}건)**")
                    for c in comp_pending:
                        st.markdown(f"- ❌ {c.item}")
                        if c.previous_finding:
                            st.caption(f"   이전 지적: {c.previous_finding[:100]}")

                st.divider()

            st.divider()

            # --- Revision email (Korean + English tabs) ---
            st.markdown("### 📧 수정 안내 메일")
            if report.revision_items:
                st.markdown("**수정 항목 요약:**")
                for i, item in enumerate(report.revision_items, 1):
                    st.markdown(f"{i}. {item}")
                st.markdown("")

            email_tab_ko, email_tab_en = st.tabs(["🇰🇷 한국어", "🇺🇸 English"])

            with email_tab_ko:
                email_text_ko = st.text_area(
                    "한국어 메일 (편집 가능)",
                    value=report.email_draft,
                    height=350,
                    key="email_draft_ko",
                )
                col_ko1, col_ko2, _ = st.columns([1, 1, 2])
                with col_ko1:
                    st.download_button(
                        label="📥 한국어 메일 다운로드",
                        data=email_text_ko,
                        file_name="revision_request_ko.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )
                with col_ko2:
                    if st.button("📋 복사", key="copy_email_ko", use_container_width=True):
                        st.components.v1.html(
                            f'<script>navigator.clipboard.writeText({json.dumps(email_text_ko)});</script>',
                            height=0,
                        )
                        st.toast("클립보드에 복사되었습니다!")

            with email_tab_en:
                email_en_value = report.email_draft_en if report.email_draft_en else "(영어 버전이 생성되지 않았습니다. 검수를 다시 실행해주세요.)"
                email_text_en = st.text_area(
                    "English email (editable)",
                    value=email_en_value,
                    height=350,
                    key="email_draft_en",
                )
                col_en1, col_en2, _ = st.columns([1, 1, 2])
                with col_en1:
                    st.download_button(
                        label="📥 Download English email",
                        data=email_text_en,
                        file_name="revision_request_en.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )
                with col_en2:
                    if st.button("📋 Copy", key="copy_email_en", use_container_width=True):
                        st.components.v1.html(
                            f'<script>navigator.clipboard.writeText({json.dumps(email_text_en)});</script>',
                            height=0,
                        )
                        st.toast("Copied to clipboard!")

            st.divider()

        # --- Passed scenes (collapsible) ---
        passed_scenes = [sr for sr in report.scene_reviews if sr.status == "pass"]
        if passed_scenes:
            with st.expander(f"✅ 통과 장면 ({len(passed_scenes)}개)", expanded=False):
                for sr in passed_scenes:
                    frames_html = _get_scene_frames_html(sr.matched_time_range, _pv, "pass")
                    st.markdown(
                        f'<div class="scene-card scene-card-pass">'
                        f'<div class="scene-header">'
                        f'<div class="scene-badge scene-badge-pass">✅</div>'
                        f'<div class="scene-title">Scene {sr.scene_number}</div>'
                        f'<div class="scene-time">{sr.matched_time_range or ""}</div>'
                        f'</div>'
                        f'<div class="scene-body">'
                        f'{frames_html}'
                        f'<div class="guideline-label">가이드라인</div>'
                        f'<div class="guideline-text">{sr.guideline_description}</div>'
                        f'<div class="findings-text">{sr.findings}</div>'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )

        # --- Compliant rules (collapsible) ---
        compliant = [r for r in report.rule_reviews if r.status == "compliant"]
        if compliant:
            with st.expander(f"✅ 준수 규칙 ({len(compliant)}개)", expanded=False):
                for r in compliant:
                    st.markdown(f"- ✅ **[{r.rule_category}]** {r.rule_description}")

        # --- Mandatory Check ---
        if report.mandatory_check:
            with st.expander("📎 필수 요소 체크", expanded=False):
                items_html = []
                for elem, checked in report.mandatory_check.items():
                    icon = "✅" if checked else "❌"
                    cls = "" if checked else " mandatory-item-fail"
                    items_html.append(
                        f'<div class="mandatory-item{cls}">{icon} {elem}</div>'
                    )
                st.markdown(
                    f'<div class="mandatory-grid">{"".join(items_html)}</div>',
                    unsafe_allow_html=True,
                )

    else:
        st.info("검수가 완료되면 여기에 결과가 표시됩니다.")


# ===== Tab 3: Editing Tips =====
with tab3:
    if "review_report" in st.session_state:
        import base64 as _b64
        import re as _re

        report: ReviewReport = st.session_state["review_report"]

        if report.editing_tips:
            category_names = {
                "font": "폰트/자막",
                "effect": "효과/이펙트",
                "transition": "전환/트랜지션",
                "layout": "레이아웃/구도",
                "sfx": "사운드/효과음",
                "general": "일반 편집",
            }

            # --- Build scene→thumbnail mapping from video frames ---
            scene_thumbs = {}
            processed_video = st.session_state.get("processed_video")
            if processed_video and report.scene_reviews:
                for sr in report.scene_reviews:
                    m = _re.search(r"([\d.]+)\s*[-~]\s*([\d.]+)", sr.matched_time_range or "")
                    if m:
                        t_start = float(m.group(1))
                        t_mid = (t_start + float(m.group(2))) / 2
                    else:
                        t_mid = None

                    if t_mid is not None:
                        best_frame = min(
                            processed_video.frames,
                            key=lambda f: abs(f.timestamp - t_mid),
                        )
                        scene_thumbs[sr.scene_number] = _b64.b64encode(
                            best_frame.image_bytes
                        ).decode("utf-8")

            # --- Build table HTML ---
            html = ['<div class="tips-wrap"><table class="tips-table">']
            html.append(
                "<thead><tr>"
                "<th>장면</th>"
                "<th>카테고리</th>"
                "<th>편집 팁</th>"
                "<th>캡컷 폰트</th>"
                "<th>캡컷 SFX</th>"
                "</tr></thead><tbody>"
            )

            for tip in report.editing_tips:
                cat = tip.category
                tag_class = f"tag-{cat}" if cat in category_names else "tag-general"
                cat_label = category_names.get(cat, cat)
                scene_num = tip.scene_number
                scene_label = f"Scene {scene_num}" if scene_num > 0 else "전체"

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

            # Download as text for creator
            tips_text = "🎨 편집 가이드 (캡컷 기준)\n" + "=" * 40 + "\n\n"
            for tip in report.editing_tips:
                scene_label = f"Scene {tip.scene_number}" if tip.scene_number > 0 else "전체"
                tips_text += f"[{scene_label}] [{category_names.get(tip.category, tip.category)}]\n"
                tip_items = tip.tip if isinstance(tip.tip, list) else [tip.tip]
                for item in tip_items:
                    tips_text += f"  → {item}\n"
                if tip.font_names:
                    tips_text += f"  폰트: {', '.join(tip.font_names)}\n"
                if tip.sfx_names:
                    tips_text += f"  SFX: {', '.join(tip.sfx_names)}\n"
                if tip.capcut_how:
                    tips_text += f"  캡컷: {tip.capcut_how}\n"
                tips_text += "\n"

            st.download_button(
                label="📥 편집 가이드 다운로드 (.txt)",
                data=tips_text,
                file_name="editing_tips.txt",
                mime="text/plain",
            )
        else:
            st.info("검수가 완료되면 편집 팁이 생성됩니다.")
    else:
        st.info("검수가 완료되면 편집 팁이 생성됩니다.")


# ===== Tab 4: Brand Sheet Comment =====
with tab4:
    if "review_report" in st.session_state:
        report: ReviewReport = st.session_state["review_report"]

        st.markdown("### 📊 브랜드사 전달용 코멘트")
        st.caption("검수 결과를 브랜드사 공유 시트에 붙여넣을 수 있는 형태로 정리했습니다.")

        brand_tab_ko, brand_tab_en = st.tabs(["🇰🇷 한국어", "🇺🇸 English"])

        with brand_tab_ko:
            brand_ko = report.brand_sheet_comment or "(브랜드 코멘트가 생성되지 않았습니다.)"
            brand_text_ko = st.text_area(
                "한국어 코멘트 (편집 가능)",
                value=brand_ko,
                height=300,
                key="brand_comment_ko",
            )
            col_bk1, col_bk2, _ = st.columns([1, 1, 2])
            with col_bk1:
                st.download_button(
                    label="📥 다운로드",
                    data=brand_text_ko,
                    file_name="brand_comment_ko.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with col_bk2:
                if st.button("📋 복사", key="copy_brand_ko", use_container_width=True):
                    st.components.v1.html(
                        f'<script>navigator.clipboard.writeText({json.dumps(brand_text_ko)});</script>',
                        height=0,
                    )
                    st.toast("클립보드에 복사되었습니다!")

        with brand_tab_en:
            brand_en = report.brand_sheet_comment_en or "(English comment not generated.)"
            brand_text_en = st.text_area(
                "English comment (editable)",
                value=brand_en,
                height=300,
                key="brand_comment_en",
            )
            col_be1, col_be2, _ = st.columns([1, 1, 2])
            with col_be1:
                st.download_button(
                    label="📥 Download",
                    data=brand_text_en,
                    file_name="brand_comment_en.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with col_be2:
                if st.button("📋 Copy", key="copy_brand_en", use_container_width=True):
                    st.components.v1.html(
                        f'<script>navigator.clipboard.writeText({json.dumps(brand_text_en)});</script>',
                        height=0,
                    )
                    st.toast("Copied to clipboard!")

        # Review history section
        if "parsed_guideline" in st.session_state:
            g = st.session_state["parsed_guideline"]
            campaign_id = g.title or g.product_name or "default"
            history = db.list_reviews(campaign_id)
            if history:
                st.divider()
                st.markdown("### 📋 검수 이력")
                _decision_map = {
                    "approved": "✅수동승인",
                    "auto_approved": "🤖자동승인",
                    "rejected": "❌수동반려",
                    "revision_needed": "📝수동수정요청",
                }
                for h in history[:10]:
                    score = h.get("overall_score", 0)
                    score_color = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")
                    status_icon = {"approved": "✅", "revision_needed": "📝", "rejected": "❌"}.get(h.get("overall_status", ""), "❓")
                    ts = h["created_at"][:16].replace("T", " ") if h.get("created_at") else ""
                    ad = h.get("admin_decision")
                    ad_badge = f" | {_decision_map.get(ad, '')}" if ad else ""
                    st.markdown(
                        f"- {score_color} **{h['creator_name']}** — Round {h['round']} | "
                        f"점수: {score} {status_icon}{ad_badge} | {ts}"
                    )
        # --- Brand Feedback Input (PHASE 3) ---
        st.divider()
        st.markdown("### 💬 브랜드 피드백 전달")
        st.caption("고객사(브랜드)의 피드백을 크리에이터의 최신 리뷰에 저장합니다. 크리에이터가 자신의 페이지에서 확인할 수 있습니다.")

        if "parsed_guideline" in st.session_state:
            g = st.session_state["parsed_guideline"]
            bf_campaign = g.title or g.product_name or "default"

            bf_submissions = db.get_submission_status(bf_campaign)
            bf_creators = [s["creator_name"] for s in bf_submissions] if bf_submissions else []

            if bf_creators:
                bf_creator = st.selectbox(
                    "크리에이터 선택",
                    bf_creators,
                    key="bf_creator_select",
                )
                # Find this creator's latest review ID
                bf_sub = next((s for s in bf_submissions if s["creator_name"] == bf_creator), None)
                bf_review_id = bf_sub["id"] if bf_sub else None

                # Show existing feedback on this review
                if bf_sub and bf_sub.get("brand_feedback"):
                    st.info(f"**기존 피드백:** {bf_sub['brand_feedback']}")

                bf_text = st.text_area(
                    "브랜드 피드백 내용",
                    placeholder="예: 제품 클로즈업 장면에서 로고가 더 잘 보이도록 수정 요청\n예: 후반 CTA 멘트를 '지금 바로 확인하세요'로 변경",
                    height=150,
                    key="bf_feedback_text",
                )
                if st.button("📤 피드백 전달", key="bf_submit", use_container_width=True):
                    if bf_text.strip() and bf_review_id:
                        db.save_brand_feedback(bf_review_id, bf_text.strip())
                        st.success(f"✅ {bf_creator}에게 피드백이 전달되었습니다.")
                        st.rerun()
                    elif not bf_text.strip():
                        st.warning("피드백 내용을 입력해주세요.")
            else:
                st.info("제출한 크리에이터가 없어 피드백을 전달할 대상이 없습니다.")

    else:
        st.info("검수가 완료되면 브랜드사 전달용 코멘트가 생성됩니다.")


# ===== Tab 5: Upload Check =====
with tab5:
    st.markdown("### 🔗 업로드 후 확인")
    st.caption("크리에이터가 업로드한 게시물의 캡션에 필수 요소(해시태그, 멘션, 광고 표시 등)가 포함되었는지 확인합니다.")

    upload_input_mode = st.radio(
        "입력 방식",
        ["URL 링크", "캡션 직접 붙여넣기"],
        horizontal=True,
        key="upload_input_mode",
    )

    post_url = ""
    post_content = ""

    if upload_input_mode == "URL 링크":
        post_url = st.text_input(
            "게시물 URL",
            placeholder="YouTube, Instagram, TikTok 링크 붙여넣기",
            key="upload_check_url",
        )
        st.caption("지원: YouTube, Instagram, TikTok (공개 게시물)")
    else:
        post_content = st.text_area(
            "게시물 캡션 붙여넣기",
            placeholder="크리에이터가 업로드한 게시물의 캡션/설명을 여기에 붙여넣으세요.\n\n예:\n오늘도 피부 관리! #광고 #skincare @brandname ...",
            height=200,
            key="upload_check_content",
        )

    has_input = bool(post_url.strip()) or bool(post_content.strip())
    check_btn = st.button(
        "🔍 캡션 확인",
        disabled=not (has_input and "parsed_guideline" in st.session_state),
        use_container_width=True,
        key="upload_check_btn",
    )

    if check_btn and has_input and "parsed_guideline" in st.session_state:
        from analyzer.upload_checker import check_upload, fetch_post_content

        guideline = st.session_state["parsed_guideline"]

        # Fetch content from URL if needed
        if post_url.strip() and not post_content.strip():
            with st.spinner("게시물 캡션 가져오는 중..."):
                try:
                    platform, fetched_content = fetch_post_content(post_url.strip())
                    post_content = fetched_content
                    st.success(f"✅ {platform}에서 캡션을 가져왔습니다.")
                    with st.expander("가져온 캡션 내용", expanded=False):
                        st.text(post_content[:2000])
                except ValueError as e:
                    st.error(str(e))
                    post_content = ""

        if post_content.strip():
            with st.spinner("캡션 필수 요소 확인 중..."):
                try:
                    result = check_upload(post_content, guideline)
                    st.session_state["upload_check_result"] = result
                    # Save to DB if we have a review ID
                    _cap_rid = st.session_state.get("last_review_id")
                    if _cap_rid:
                        db.save_caption_check(_cap_rid, result)
                except Exception as e:
                    st.error(f"확인 오류: {e}")

    if "upload_check_result" in st.session_state:
        result = st.session_state["upload_check_result"]
        all_passed = result.get("all_passed", False)

        if all_passed:
            st.success("✅ 모든 필수 요소가 확인되었습니다!")
        else:
            st.warning("⚠️ 누락된 항목이 있습니다.")

        checks = result.get("checks", [])
        if checks:
            for check in checks:
                status = check.get("status", "")
                element = check.get("element", "")
                detail = check.get("detail", "")

                if status == "found":
                    st.markdown(f"- ✅ **{element}** — {detail}")
                elif status == "missing":
                    st.markdown(f"- ❌ **{element}** — {detail}")
                else:
                    st.markdown(f"- 🟡 **{element}** — {detail}")

        st.markdown("---")
        st.markdown(f"**요약:** {result.get('summary_ko', '')}")

    elif not ("parsed_guideline" in st.session_state):
        st.info("가이드라인을 먼저 파싱해주세요. 가이드라인의 필수 요소를 기준으로 확인합니다.")

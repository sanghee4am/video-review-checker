from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import ANTHROPIC_API_KEY, OPENAI_API_KEY
from models.guideline import ParsedGuideline
from models.review_result import ReviewReport

# --- Saved Guidelines ---
SAVED_GUIDELINES_DIR = Path(__file__).parent / "saved_guidelines"
SAVED_GUIDELINES_DIR.mkdir(exist_ok=True)


def _list_saved_guidelines() -> list[tuple[str, Path]]:
    """Return list of (display_name, file_path) sorted by newest first."""
    files = sorted(SAVED_GUIDELINES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for f in files:
        try:
            meta = json.loads(f.read_text(encoding="utf-8"))
            name = meta.get("campaign_name", f.stem)
            result.append((name, f))
        except Exception:
            result.append((f.stem, f))
    return result


def _save_guideline(campaign_name: str, guideline: ParsedGuideline) -> Path:
    """Save parsed guideline as JSON."""
    safe_name = "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in campaign_name).strip()
    filepath = SAVED_GUIDELINES_DIR / f"{safe_name}.json"
    data = {
        "campaign_name": campaign_name,
        "guideline": guideline.model_dump(),
    }
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def _load_guideline(filepath: Path) -> tuple[str, ParsedGuideline]:
    """Load guideline from JSON file."""
    data = json.loads(filepath.read_text(encoding="utf-8"))
    guideline = ParsedGuideline.model_validate(data["guideline"])
    return data["campaign_name"], guideline

st.set_page_config(
    page_title="Video Guideline Checker",
    page_icon="🎬",
    layout="wide",
)

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
</style>
""", unsafe_allow_html=True)

st.title("🎬 영상 가이드라인 검수 자동화")
st.caption("크리에이터 영상이 가이드라인에 부합하는지 AI로 1차 검수합니다.")

# --- Sidebar: File Uploads ---
with st.sidebar:
    st.header("📂 입력")

    st.subheader("1. 가이드라인")

    # Saved guidelines loader
    saved_list = _list_saved_guidelines()
    if saved_list:
        saved_names = ["— 새로 업로드 —"] + [name for name, _ in saved_list]
        saved_selection = st.selectbox(
            "저장된 가이드라인",
            saved_names,
            key="saved_guideline_select",
        )
        if saved_selection != "— 새로 업로드 —":
            match = next((fp for name, fp in saved_list if name == saved_selection), None)
            if match:
                load_btn = st.button("📂 불러오기", key="load_saved_gl", use_container_width=True)
                if load_btn:
                    camp_name, loaded_gl = _load_guideline(match)
                    st.session_state["parsed_guideline"] = loaded_gl
                    st.session_state["guideline_images"] = []
                    st.success(f"'{camp_name}' 가이드라인 불러옴!")
                    st.rerun()

                # Delete button
                del_btn = st.button("🗑️ 삭제", key="delete_saved_gl", use_container_width=True)
                if del_btn:
                    match.unlink()
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

    st.subheader("2. 크리에이터 영상")
    video_files = st.file_uploader(
        "영상 파일 업로드 (여러 개 가능)",
        type=["mp4", "mov", "avi", "mkv"],
        accept_multiple_files=True,
        key="video_upload",
    )

    st.subheader("3. 메모 (선택)")
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

    parse_btn = st.button(
        "📋 가이드라인 파싱",
        disabled=not (has_guideline_input and api_ok),
        use_container_width=True,
    )

    review_btn = st.button(
        "🔍 검수 시작",
        disabled=not (
            "parsed_guideline" in st.session_state
            and video_files
            and api_ok
        ),
        use_container_width=True,
        type="primary",
    )

# --- Main Area ---
tab1, tab2, tab3 = st.tabs(["📋 가이드라인", "🔍 검수 결과", "🎨 편집 팁"])

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
                        _save_guideline(campaign_name.strip(), g)
                        st.session_state["show_save_guideline"] = False
                        st.success(f"'{campaign_name}' 저장 완료! 사이드바에서 불러올 수 있습니다.")
                        st.rerun()
                    else:
                        st.warning("캠페인 이름을 입력해주세요.")

    else:
        st.info("👈 사이드바에서 가이드라인 파일을 업로드하고 '가이드라인 파싱' 버튼을 눌러주세요.")

# ===== Video Review (multi-video batch) =====
if review_btn and video_files and "parsed_guideline" in st.session_state:
    from processors.video_processor import process_video, process_videos_parallel
    from analyzer.compliance_checker import run_compliance_check

    guideline = st.session_state["parsed_guideline"]
    guideline_images = st.session_state.get("guideline_images", [])
    num_videos = len(video_files)

    progress_bar = st.progress(0, text=f"영상 {num_videos}개 처리 준비 중...")

    try:
        # --- Phase 1: Parallel preprocessing (ffmpeg + Whisper) ---
        progress_bar.progress(5, text=f"영상 {num_videos}개 병렬 전처리 중 (프레임 추출 + STT)...")

        video_items = []
        for vf in video_files:
            video_items.append((vf.name, vf.read()))

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

        progress_bar.progress(100, text=f"검수 완료! ({num_videos}개 영상)")
        st.success(f"검수가 완료되었습니다! {num_videos}개 영상의 결과를 '검수 결과' 탭에서 확인하세요.")

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
        score_class = "hero-score-high" if score >= 80 else ("hero-score-mid" if score >= 60 else "hero-score-low")
        status_labels = {
            "approved": "✅ 승인 — 수정 없이 게시 가능",
            "revision_needed": "📝 수정 필요 — 아래 항목 확인 후 재촬영/편집",
            "rejected": "❌ 반려 — 가이드라인 재확인 필요",
        }
        status_label = status_labels.get(report.overall_status, "❓ 미정")

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
        has_issues = (n_violated > 0 or s_fail > 0 or n_manual > 0)

        if has_issues and report.overall_status != "approved":
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

            st.divider()

            # --- Revision email (inline, not separate tab) ---
            st.markdown("### 📧 수정 안내 메일")
            if report.revision_items:
                st.markdown("**수정 항목 요약:**")
                for i, item in enumerate(report.revision_items, 1):
                    st.markdown(f"{i}. {item}")
                st.markdown("")

            email_text = st.text_area(
                "메일 내용 (편집 가능)",
                value=report.email_draft,
                height=300,
                key="email_draft_editor",
            )

            col_dl1, col_dl2, _ = st.columns([1, 1, 2])
            with col_dl1:
                st.download_button(
                    label="📥 메일 다운로드",
                    data=email_text,
                    file_name="revision_request.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with col_dl2:
                st.button("📋 클립보드 복사", key="copy_email", use_container_width=True)

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

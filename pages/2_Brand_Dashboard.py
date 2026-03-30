"""Brand Review Dashboard.

고객사(브랜드)가 캠페인별 링크로 접근하여:
1. 크리에이터 검수 현황 확인
2. 크리에이터별 상세 검수 결과 확인
3. 피드백/코멘트 작성
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.review_result import ReviewReport
import db

st.set_page_config(
    page_title="Brand Review Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Hide sidebar completely ---
st.markdown("""
<style>
    [data-testid="stSidebarNav"] { display: none !important; }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] > div:first-child { display: none !important; }
    button[data-testid="stSidebarCollapsedControl"] { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }

    .block-container { padding-top: 1.5rem; max-width: 960px; }

    /* ===== Brand Header ===== */
    .brand-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border-radius: 16px; padding: 32px 40px; color: #fff;
        margin-bottom: 24px;
    }
    .brand-header h1 {
        margin: 0 0 4px 0; font-size: 28px; font-weight: 800;
    }
    .brand-header .brand-sub {
        font-size: 14px; color: #94a3b8;
    }

    /* ===== Metric Cards ===== */
    .metric-row { display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
    .metric-card {
        flex: 1; min-width: 140px; background: #f8fafc;
        border: 1px solid #e2e8f0; border-radius: 12px;
        padding: 20px; text-align: center;
    }
    .metric-value {
        font-size: 32px; font-weight: 800; line-height: 1.2;
    }
    .metric-label {
        font-size: 12px; color: #64748b; margin-top: 4px; font-weight: 500;
    }
    .metric-green { color: #16a34a; }
    .metric-yellow { color: #d97706; }
    .metric-blue { color: #2563eb; }

    /* ===== Progress Bar ===== */
    .progress-bar-wrap {
        background: #e2e8f0; border-radius: 8px; height: 10px;
        margin-bottom: 24px; overflow: hidden; display: flex;
    }
    .progress-seg-approved { background: #22c55e; height: 100%; }
    .progress-seg-revision { background: #f59e0b; height: 100%; }
    .progress-seg-pending { background: #cbd5e1; height: 100%; }

    /* ===== Hero Score Card ===== */
    .hero-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 16px; padding: 24px 32px; color: #fff;
        display: flex; align-items: center; gap: 28px;
        margin-bottom: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    }
    .hero-score {
        font-size: 56px; font-weight: 800; line-height: 1;
        min-width: 80px; text-align: center;
    }
    .hero-score-high { color: #4ade80; }
    .hero-score-mid { color: #facc15; }
    .hero-score-low { color: #f87171; }
    .hero-info { flex: 1; }
    .hero-status { font-size: 18px; font-weight: 700; margin-bottom: 4px; }
    .hero-summary { font-size: 13px; color: #cbd5e1; line-height: 1.5; }
    .hero-stats { display: flex; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
    .hero-stat {
        background: rgba(255,255,255,0.1); border-radius: 8px;
        padding: 5px 12px; font-size: 11px; color: #e2e8f0;
    }
    .hero-stat b { color: #fff; }

    /* ===== Scene Cards ===== */
    .scene-card {
        border: 1px solid #e5e7eb; border-radius: 12px;
        margin-bottom: 10px; overflow: hidden;
    }
    .scene-card-fail { border-left: 4px solid #ef4444; }
    .scene-card-warning { border-left: 4px solid #f59e0b; }
    .scene-card-pass { border-left: 4px solid #22c55e; }
    .scene-header {
        display: flex; align-items: center; gap: 12px;
        padding: 12px 16px; background: #fafafa;
        border-bottom: 1px solid #f0f0f0;
    }
    .scene-badge {
        display: inline-flex; align-items: center; justify-content: center;
        width: 26px; height: 26px; border-radius: 50%;
        font-size: 13px; font-weight: 700; flex-shrink: 0;
    }
    .scene-badge-pass { background: #dcfce7; color: #166534; }
    .scene-badge-fail { background: #fee2e2; color: #991b1b; }
    .scene-badge-warning { background: #fef3c7; color: #92400e; }
    .scene-title { font-weight: 600; font-size: 13px; flex: 1; }
    .scene-time { font-size: 11px; color: #9ca3af; }
    .scene-body { padding: 14px 16px; }
    .scene-body .guideline-label {
        font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;
        color: #9ca3af; font-weight: 600; margin-bottom: 3px;
    }
    .scene-body .guideline-text {
        font-size: 12px; color: #6b7280; margin-bottom: 8px;
        padding-left: 10px; border-left: 2px solid #e5e7eb;
    }
    .scene-body .findings-text {
        font-size: 12px; color: #1f2937; line-height: 1.6; margin-bottom: 8px;
    }
    .scene-suggestion {
        background: #fff7ed; border: 1px solid #fed7aa;
        border-radius: 8px; padding: 8px 12px;
        font-size: 12px; color: #9a3412;
    }
    .scene-suggestion-label {
        font-weight: 700; font-size: 10px; text-transform: uppercase;
        letter-spacing: 0.5px; margin-bottom: 2px; color: #c2410c;
    }

    /* ===== Evidence Frames ===== */
    .evidence-frames { display: flex; gap: 6px; margin: 8px 0; flex-wrap: wrap; }
    .evidence-frame { display: inline-block; text-align: center; flex-shrink: 0; }
    .evidence-frame img {
        width: 100px; height: auto; border-radius: 6px;
        border: 2px solid #e0e0e0; object-fit: cover;
    }
    .evidence-frame-fail img { border-color: #ef4444; }
    .evidence-frame-warning img { border-color: #f59e0b; }
    .evidence-frame-pass img { border-color: #22c55e; }

    /* ===== Rule Cards ===== */
    .rule-card {
        border-radius: 10px; padding: 12px 16px;
        margin-bottom: 6px; font-size: 12px; line-height: 1.6;
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
        border-radius: 4px; padding: 1px 6px; font-size: 10px;
        font-weight: 600; text-transform: uppercase; margin-right: 4px;
    }
    .rule-desc { font-weight: 600; color: #1f2937; }
    .rule-evidence { color: #6b7280; margin-top: 3px; }
    .rule-suggestion { color: #b45309; font-weight: 500; margin-top: 3px; }

    /* ===== Mandatory Grid ===== */
    .mandatory-grid { display: flex; flex-wrap: wrap; gap: 6px; }
    .mandatory-item {
        display: inline-flex; align-items: center; gap: 4px;
        background: #f8fafc; border: 1px solid #e2e8f0;
        border-radius: 8px; padding: 6px 12px; font-size: 12px;
    }
    .mandatory-item-fail { border-color: #fecaca; background: #fef2f2; }

    /* ===== Manual Review ===== */
    .manual-flag {
        background: #fffbeb; border: 1px solid #fde68a;
        border-radius: 8px; padding: 10px 14px;
        margin-bottom: 6px; font-size: 12px;
    }

    /* ===== Feedback ===== */
    .feedback-existing {
        background: #f0f9ff; border: 1px solid #bae6fd;
        border-radius: 10px; padding: 14px 18px;
        font-size: 13px; color: #0c4a6e; margin-bottom: 12px;
    }
    .feedback-label {
        font-size: 11px; font-weight: 700; color: #0369a1;
        text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ===== Campaign Validation =====
campaign_name = st.query_params.get("campaign", "")

if not campaign_name:
    st.markdown("### 📊 Brand Review Dashboard")
    st.info("캠페인 링크를 통해 접근해주세요.\n\n예: `?campaign=캠페인명`")
    st.stop()

# Verify campaign exists (search by campaign_name through list_guidelines)
_all_gl = db.list_guidelines()
_matched_gl = next((row for row in _all_gl if row.get("campaign_name") == campaign_name), None)
if _matched_gl is None:
    st.error(f"'{campaign_name}' 캠페인을 찾을 수 없습니다. 링크를 확인해주세요.")
    st.stop()

guideline = db.load_guideline(_matched_gl["id"])


# ===== Header =====
st.markdown(
    f'<div class="brand-header">'
    f'<h1>{campaign_name}</h1>'
    f'<div class="brand-sub">영상 검수 현황 대시보드</div>'
    f'</div>',
    unsafe_allow_html=True,
)


# ===== Load Data =====
submissions = db.get_submission_status(campaign_name)
all_reviews = db.list_reviews(campaign_name)

if not submissions:
    st.info("아직 제출된 검수 결과가 없습니다.")
    st.stop()


# ===== Overview Metrics =====
total_creators = len(submissions)
avg_score = round(sum(s.get("overall_score", 0) for s in submissions) / total_creators) if total_creators else 0
n_approved = sum(1 for s in submissions if s.get("admin_decision") in ("approved", "auto_approved"))
n_revision = sum(
    1 for s in submissions
    if s.get("admin_decision") == "revision_needed"
    or (not s.get("admin_decision") and s.get("overall_status") == "revision_needed")
)
n_pending = total_creators - n_approved - n_revision

score_color = "metric-green" if avg_score >= 80 else ("metric-yellow" if avg_score >= 60 else "")

st.markdown(
    f'<div class="metric-row">'
    f'<div class="metric-card"><div class="metric-value metric-blue">{total_creators}</div>'
    f'<div class="metric-label">크리에이터</div></div>'
    f'<div class="metric-card"><div class="metric-value {score_color}">{avg_score}</div>'
    f'<div class="metric-label">평균 점수</div></div>'
    f'<div class="metric-card"><div class="metric-value metric-green">{n_approved}</div>'
    f'<div class="metric-label">승인 완료</div></div>'
    f'<div class="metric-card"><div class="metric-value metric-yellow">{n_revision}</div>'
    f'<div class="metric-label">수정 대기</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)

# Progress bar
if total_creators > 0:
    pct_approved = round(n_approved / total_creators * 100)
    pct_revision = round(n_revision / total_creators * 100)
    pct_pending = 100 - pct_approved - pct_revision
    st.markdown(
        f'<div class="progress-bar-wrap">'
        f'<div class="progress-seg-approved" style="width:{pct_approved}%"></div>'
        f'<div class="progress-seg-revision" style="width:{pct_revision}%"></div>'
        f'<div class="progress-seg-pending" style="width:{pct_pending}%"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    legend_parts = []
    if n_approved:
        legend_parts.append(f"🟢 승인 {n_approved}명")
    if n_revision:
        legend_parts.append(f"🟡 수정대기 {n_revision}명")
    if n_pending:
        legend_parts.append(f"⚪ 검토중 {n_pending}명")
    st.caption(" · ".join(legend_parts))


# ===== Helper: Render brand review =====
def _render_brand_review(report: ReviewReport):
    """Render review for brand view (no admin controls, no editing tips, no email drafts)."""
    score = report.overall_score
    score_class = "hero-score-high" if score >= 90 else ("hero-score-mid" if score >= 60 else "hero-score-low")

    _display_status = report.overall_status
    if score < 90 and _display_status == "approved":
        _display_status = "revision_needed"

    status_labels = {
        "approved": "✅ 승인 — 수정 없이 게시 가능",
        "revision_needed": "📝 수정 필요 — 수정 후 재제출 예정",
        "rejected": "❌ 반려 — 재촬영 필요",
    }
    status_label = status_labels.get(_display_status, "❓ 검토 중")

    s_pass = sum(1 for s in report.scene_reviews if s.status == "pass")
    s_fail = sum(1 for s in report.scene_reviews if s.status == "fail")
    s_warn = sum(1 for s in report.scene_reviews if s.status == "warning")
    n_violated = sum(1 for r in report.rule_reviews if r.status == "violated")

    st.markdown(
        f'<div class="hero-card">'
        f'<div class="hero-score {score_class}">{score}</div>'
        f'<div class="hero-info">'
        f'<div class="hero-status">{status_label}</div>'
        f'<div class="hero-summary">{report.summary}</div>'
        f'<div class="hero-stats">'
        f'<div class="hero-stat">장면 <b>✅{s_pass}</b> ❌{s_fail} ⚠️{s_warn}</div>'
        f'<div class="hero-stat">규칙 위반 <b>{n_violated}건</b></div>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    # Issues
    has_issues = (n_violated > 0 or s_fail > 0 or s_warn > 0)
    if has_issues:
        st.markdown("#### 🚨 수정 필요 항목")

        problem_scenes = [sr for sr in report.scene_reviews if sr.status in ("fail", "warning")]
        for sr in problem_scenes:
            status = sr.status
            icon = "❌" if status == "fail" else "⚠️"

            frames_html = ""
            if report.scene_thumbnails and str(sr.scene_number) in report.scene_thumbnails:
                frames_html = (
                    f'<div class="evidence-frames">'
                    f'<div class="evidence-frame evidence-frame-{status}">'
                    f'<img src="data:image/jpeg;base64,{report.scene_thumbnails[str(sr.scene_number)]}" />'
                    f'</div></div>'
                )

            suggestion_html = ""
            if sr.suggestion:
                suggestion_html = (
                    f'<div class="scene-suggestion">'
                    f'<div class="scene-suggestion-label">수정 제안</div>'
                    f'{sr.suggestion}</div>'
                )

            st.markdown(
                f'<div class="scene-card scene-card-{status}">'
                f'<div class="scene-header">'
                f'<div class="scene-badge scene-badge-{status}">{icon}</div>'
                f'<div class="scene-title">Scene {sr.scene_number}</div>'
                f'<div class="scene-time">{sr.matched_time_range or ""}</div>'
                f'</div>'
                f'<div class="scene-body">'
                f'{frames_html}'
                f'<div class="guideline-label">가이드라인 요구사항</div>'
                f'<div class="guideline-text">{sr.guideline_description}</div>'
                f'<div class="findings-text">{sr.findings}</div>'
                f'{suggestion_html}'
                f'</div></div>',
                unsafe_allow_html=True,
            )

        violated = [r for r in report.rule_reviews if r.status == "violated"]
        if violated:
            st.markdown("##### 규칙 위반")
            for r in violated:
                st.markdown(
                    f'<div class="rule-card rule-violated">'
                    f'<span class="rule-cat">{r.rule_category}</span>'
                    f'<span class="rule-desc">{r.rule_description}</span>'
                    f'<div class="rule-evidence">근거: {r.evidence}</div>'
                    f'<div class="rule-suggestion">💡 {r.suggestion}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # Passed scenes (collapsed)
    passed_scenes = [sr for sr in report.scene_reviews if sr.status == "pass"]
    if passed_scenes:
        with st.expander(f"✅ 통과 장면 ({len(passed_scenes)}개)", expanded=False):
            for sr in passed_scenes:
                frames_html = ""
                if report.scene_thumbnails and str(sr.scene_number) in report.scene_thumbnails:
                    frames_html = (
                        f'<div class="evidence-frames">'
                        f'<div class="evidence-frame evidence-frame-pass">'
                        f'<img src="data:image/jpeg;base64,{report.scene_thumbnails[str(sr.scene_number)]}" />'
                        f'</div></div>'
                    )
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

    # Compliant rules (collapsed)
    compliant = [r for r in report.rule_reviews if r.status == "compliant"]
    if compliant:
        with st.expander(f"✅ 준수 규칙 ({len(compliant)}개)", expanded=False):
            for r in compliant:
                st.markdown(f"- ✅ **[{r.rule_category}]** {r.rule_description}")

    # Mandatory check
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


# ===== Creator Cards =====
st.markdown("---")
st.markdown("### 크리에이터별 검수 결과")

# Draft filter
_rounds_set = sorted(set(r.get("round", 1) for r in all_reviews))
if len(_rounds_set) > 1:
    _filter_options = ["전체"] + [f"Draft {d}" for d in _rounds_set]
    _selected_draft = st.radio(
        "Draft 필터",
        _filter_options,
        horizontal=True,
        key="brand_draft_filter",
        label_visibility="collapsed",
    )
    if _selected_draft != "전체":
        _draft_num = int(_selected_draft.replace("Draft ", ""))
        all_reviews = [r for r in all_reviews if r.get("round", 1) == _draft_num]

# Group all reviews by creator
from collections import OrderedDict
creators_reviews: dict[str, list[dict]] = OrderedDict()
for rev in all_reviews:
    cname = rev.get("creator_name", "?")
    if cname not in creators_reviews:
        creators_reviews[cname] = []
    creators_reviews[cname].append(rev)

for ci, (creator_name, reviews) in enumerate(creators_reviews.items()):
    latest = reviews[0]
    sc = latest.get("overall_score", 0)
    rd = latest.get("round", 1)
    ts = latest["created_at"][:10] if latest.get("created_at") else ""
    st_icon = {"approved": "✅", "revision_needed": "📝", "rejected": "❌"}.get(
        latest.get("overall_status", ""), "❓"
    )
    ad = latest.get("admin_decision", "")
    ad_map = {
        "approved": "✅ 승인", "auto_approved": "🤖 자동승인",
        "revision_needed": "📝 수정필요", "rejected": "❌ 반려",
    }
    ad_label = ad_map.get(ad, "⏳ 검토중")
    score_dot = "🟢" if sc >= 80 else ("🟡" if sc >= 60 else "🔴")

    with st.expander(
        f"{score_dot} **{creator_name}** | {sc}점 {st_icon} | Draft {rd} | {ad_label} | {ts}",
        expanded=False,
    ):
        # Video link
        _vid_url = latest.get("video_url", "")
        if _vid_url:
            st.markdown(f"🎬 [영상 보기]({_vid_url})")

        # Render review
        report = ReviewReport.model_validate(latest["report_json"])
        _render_brand_review(report)

        # --- Brand Feedback Section ---
        st.markdown("---")
        st.markdown("#### 💬 피드백")

        # Show existing feedback
        if latest.get("brand_feedback"):
            st.markdown(
                f'<div class="feedback-existing">'
                f'<div class="feedback-label">기존 피드백</div>'
                f'{latest["brand_feedback"]}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Feedback form
        fb_text = st.text_area(
            "피드백 작성",
            placeholder="수정 요청 사항이나 코멘트를 입력해주세요.\n예: 제품 클로즈업 장면에서 로고가 더 잘 보이도록 수정 요청",
            height=120,
            key=f"brand_fb_{ci}",
            label_visibility="collapsed",
        )
        if st.button("📤 피드백 전달", key=f"brand_fb_btn_{ci}", use_container_width=True):
            if fb_text.strip():
                db.save_brand_feedback(latest["id"], fb_text.strip())
                st.success("✅ 피드백이 전달되었습니다. 담당자가 확인 후 크리에이터에게 전달합니다.")
                st.rerun()
            else:
                st.warning("피드백 내용을 입력해주세요.")

        # Previous rounds
        older = reviews[1:]
        if older:
            with st.expander(f"📂 이전 드래프트 ({len(older)}건)", expanded=False):
                for old_rev in older:
                    o_sc = old_rev.get("overall_score", 0)
                    o_rd = old_rev.get("round", 1)
                    o_ts = old_rev["created_at"][:16].replace("T", " ") if old_rev.get("created_at") else ""
                    o_st = {"approved": "✅", "revision_needed": "📝", "rejected": "❌"}.get(
                        old_rev.get("overall_status", ""), "❓"
                    )
                    st.markdown(f"**Draft {o_rd}** — {o_sc}점 {o_st} ({o_ts})")
                    old_report = ReviewReport.model_validate(old_rev["report_json"])
                    st.caption(old_report.summary)
                    if old_rev.get("brand_feedback"):
                        st.info(f"💬 피드백: {old_rev['brand_feedback']}")


# ===== Footer =====
st.markdown("---")
st.caption("검수 관련 문의사항은 담당자에게 연락해주세요.")

"""
Video Review Checker — FastAPI Backend
기존 Streamlit 검수 로직을 그대로 재활용, API로만 노출
"""
import asyncio
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── 기존 모듈 그대로 import ──
from db import (
    save_guideline, list_guidelines, load_guideline, get_guideline_source_url,
    delete_guideline_parsed, save_review, list_reviews, load_review,
    get_previous_review, get_next_round, get_submission_status,
    get_creator_reviews, save_admin_decision, save_brand_feedback,
    get_latest_brand_feedback, get_campaigns_summary,
)
from models.guideline import ParsedGuideline
from models.review_result import ReviewReport
from processors.video_processor import process_video
from processors.guideline_parser import parse_guideline
from analyzer.compliance_checker import run_compliance_check
from analyzer.content_checker import check_content
from analyzer.upload_checker import fetch_post_content, check_upload
from pipeline.video_reviewer import run_pipeline_review


# ── 진행 상태 저장 (in-memory) ──
jobs: dict[str, dict] = {}


def _start_content_check_worker():
    """콘텐츠 체크 워커를 백그라운드 스레드에서 실행."""
    from pipeline.content_check_worker import run_loop
    worker = threading.Thread(target=run_loop, args=(30,), daemon=True)
    worker.start()
    print("✓ Content check worker started (polling every 30s)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_content_check_worker()
    yield
    jobs.clear()


app = FastAPI(title="Video Review Checker API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_all_requests(request, call_next):
    """모든 요청 로깅"""
    print(f"[HTTP] {request.method} {request.url.path} from {request.client.host}")
    response = await call_next(request)
    print(f"[HTTP] → {response.status_code}")
    return response


# ═══════════════════════════════════════════
# Health
# ═══════════════════════════════════════════
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ═══════════════════════════════════════════
# Guideline 관리
# ═══════════════════════════════════════════
class GuidelineUploadResult(BaseModel):
    gl_id: str
    guideline: dict


@app.post("/api/guidelines/upload", response_model=GuidelineUploadResult)
async def upload_guideline(
    gl_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """가이드라인 파일 업로드 → 파싱 → guidelines.gl_parsed_json에 저장"""
    file_items: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read()
        file_items.append((f.filename or "file", data))

    parsed, _images = parse_guideline(file_items)
    save_guideline(gl_id, parsed)
    return GuidelineUploadResult(
        gl_id=gl_id,
        guideline=parsed.model_dump(),
    )


class NotionParseRequest(BaseModel):
    gl_id: str
    notion_page_id: str


@app.post("/api/guidelines/parse-notion")
async def parse_notion_guideline(body: NotionParseRequest):
    """노션 공개 페이지에서 가이드라인을 파싱하여 gl_parsed_json에 저장"""
    from processors.url_fetcher import fetch_notion_by_page_id
    from processors.guideline_parser import parse_guideline

    # 1) 노션 페이지 내용 가져오기
    try:
        filename, file_bytes = fetch_notion_by_page_id(body.notion_page_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 2) AI 파싱
    parsed, _images = parse_guideline([(filename, file_bytes)])

    # 3) DB 저장
    save_guideline(body.gl_id, parsed)

    return {
        "gl_id": body.gl_id,
        "guideline": parsed.model_dump(),
    }


@app.get("/api/guidelines")
def api_list_guidelines():
    """파싱된 가이드라인 목록"""
    return list_guidelines()


@app.get("/api/guidelines/{gl_id}")
def api_get_guideline(gl_id: str):
    parsed = load_guideline(gl_id)
    if not parsed:
        raise HTTPException(404, "Guideline not found or not parsed")
    return {"gl_id": gl_id, "guideline": parsed.model_dump()}


@app.delete("/api/guidelines/{gl_id}")
def api_delete_guideline(gl_id: str):
    delete_guideline_parsed(gl_id)
    return {"ok": True}


# ═══════════════════════════════════════════
# 영상 검수 (비동기 Job)
# ═══════════════════════════════════════════
class ReviewJobRequest(BaseModel):
    campaign_name: str
    creator_name: str
    gl_id: str  # guidelines 테이블의 UUID


class ReviewJobResponse(BaseModel):
    job_id: str
    status: str


def _run_review_job(
    job_id: str,
    video_bytes: bytes,
    filename: str,
    campaign_name: str,
    creator_name: str,
    gl_id: str,
):
    """백그라운드에서 검수 실행"""
    import traceback as _tb
    print(f"[REVIEW JOB] START job={job_id} gl_id={gl_id} campaign={campaign_name} creator={creator_name}")
    jobs[job_id]["status"] = "processing"
    jobs[job_id]["progress"] = "영상 처리 시작"
    try:
        def progress_cb(step_or_msg, total=None, msg=None):
            if msg is not None:
                jobs[job_id]["progress"] = msg
            else:
                jobs[job_id]["progress"] = str(step_or_msg)

        # 가이드라인 로드
        print(f"[REVIEW JOB] Loading guideline gl_id={gl_id}")
        guideline = load_guideline(gl_id)
        print(f"[REVIEW JOB] Guideline loaded: {guideline is not None}")
        if not guideline:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = f"가이드라인을 찾을 수 없습니다 (gl_id={gl_id})"
            return

        # 이전 리뷰 조회 (재검수인 경우)
        prev = get_previous_review(campaign_name, creator_name)
        previous_report = prev[0] if prev else None
        review_round = (prev[1] + 1) if prev else 1
        brand_feedback = get_latest_brand_feedback(campaign_name, creator_name)

        # 영상 처리
        progress_cb("영상 프레임 추출 & STT 진행 중...")
        processed = process_video(video_bytes, filename)

        # 가이드라인 이미지 (DB에서 로드 — 현재는 빈 리스트, 향후 확장)
        guideline_images: list[bytes] = []

        # AI 검수
        progress_cb("AI 검수 진행 중...")
        report = run_compliance_check(
            guideline=guideline,
            guideline_images=guideline_images,
            video=processed,
            progress_callback=progress_cb,
            memo=None,
            brand_feedback=brand_feedback,
            previous_report=previous_report,
            review_round=review_round,
        )

        # 썸네일 첨부
        report.attach_thumbnails(processed)

        # DB 저장
        review_id = save_review(
            campaign_name=campaign_name,
            creator_name=creator_name,
            report=report,
            round_num=review_round,
            gl_id=gl_id,
        )

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {
            "review_id": review_id,
            "score": report.overall_score,
            "overall_status": report.overall_status,
            "summary": report.summary,
            "review_round": review_round,
        }

    except Exception as e:
        print(f"[REVIEW JOB] FAILED: {e}")
        _tb.print_exc()
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


class ReviewByPathRequest(BaseModel):
    ci_id: str
    storage_path: str


@app.post("/api/review-by-path", response_model=ReviewJobResponse)
async def start_review_by_path(
    body: ReviewByPathRequest,
    background_tasks: BackgroundTasks,
):
    """Storage 경로로 자동 검수 시작 (Workers에서 호출)"""
    from db import get_ci_info, download_from_storage

    ci = get_ci_info(body.ci_id)
    if not ci:
        raise HTTPException(404, f"campaign_influencer not found: {body.ci_id}")

    gl_id = ci["ci_guideline_id"]
    creator_name = ci["ci_username"]
    campaign_name = ci.get("campaigns", {}).get("cam_name", "unknown")
    is_first = not bool(ci.get("ci_1st_draft_urls"))

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "progress": "대기 중"}

    def _run():
        import traceback as _tb
        print(f"[AUTO-REVIEW] START job={job_id} ci_id={body.ci_id} path={body.storage_path}")
        jobs[job_id]["status"] = "processing"
        try:
            # Storage에서 영상 다운로드
            jobs[job_id]["progress"] = "영상 다운로드 중..."
            video_bytes = download_from_storage(body.storage_path)
            filename = body.storage_path.split("/")[-1] or "video.mp4"

            # 기존 검수 로직 재활용
            guideline = load_guideline(gl_id)
            if not guideline:
                # gl_parsed_json 이 비어있으면, gl_source_url 이 campaign-guideline-tool
                # 공유 URL 인 경우 자동으로 fetch + save 한 뒤 진행.
                from processors.external_guideline import fetch_parsed_guideline_from_share_url
                source_url = get_guideline_source_url(gl_id)
                if source_url:
                    try:
                        jobs[job_id]["progress"] = "외부 가이드라인 fetch 중..."
                        fetched = fetch_parsed_guideline_from_share_url(source_url)
                    except Exception as fetch_err:
                        print(f"[AUTO-REVIEW] external guideline fetch failed: {fetch_err}")
                        fetched = None
                    if fetched is not None:
                        save_guideline(gl_id, fetched)
                        guideline = fetched
                if not guideline:
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["error"] = f"가이드라인 없음 (gl_id={gl_id})"
                    return

            prev = get_previous_review(campaign_name, creator_name)
            previous_report = prev[0] if prev else None
            review_round = (prev[1] + 1) if prev else 1
            brand_feedback = get_latest_brand_feedback(campaign_name, creator_name)

            def progress_cb(step_or_msg, total=None, msg=None):
                if msg is not None:
                    jobs[job_id]["progress"] = msg
                else:
                    jobs[job_id]["progress"] = str(step_or_msg)

            jobs[job_id]["progress"] = "영상 프레임 추출 & STT 진행 중..."
            processed = process_video(video_bytes, filename)

            jobs[job_id]["progress"] = "AI 검수 진행 중..."
            report = run_compliance_check(
                guideline=guideline,
                guideline_images=[],
                video=processed,
                progress_callback=progress_cb,
                memo=None,
                brand_feedback=brand_feedback,
                previous_report=previous_report,
                review_round=review_round,
            )

            report.attach_thumbnails(processed)

            review_id = save_review(
                campaign_name=campaign_name,
                creator_name=creator_name,
                report=report,
                round_num=review_round,
                gl_id=gl_id,
                ci_id=body.ci_id,
            )

            # 점수에 따라 ci_status 업데이트
            from db import update_ci_status_after_review
            update_ci_status_after_review(body.ci_id, report.overall_score, is_first)

            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = {
                "review_id": review_id,
                "score": report.overall_score,
                "overall_status": report.overall_status,
                "summary": report.summary,
                "review_round": review_round,
                "ci_status_updated": report.overall_score >= 80,
            }
            print(f"[AUTO-REVIEW] DONE score={report.overall_score} ci_status_updated={report.overall_score >= 80}")

        except Exception as e:
            print(f"[AUTO-REVIEW] FAILED: {e}")
            _tb.print_exc()
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)

    background_tasks.add_task(_run)
    return ReviewJobResponse(job_id=job_id, status="queued")


@app.post("/api/review", response_model=ReviewJobResponse)
async def start_review(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    campaign_name: str = Form(...),
    creator_name: str = Form(...),
    gl_id: str = Form(...),
):
    """영상 업로드 → 백그라운드 검수 Job 시작"""
    job_id = str(uuid.uuid4())
    video_bytes = await video.read()

    jobs[job_id] = {"status": "queued", "progress": "대기 중"}
    background_tasks.add_task(
        _run_review_job, job_id, video_bytes, video.filename or "video.mp4",
        campaign_name, creator_name, gl_id,
    )
    return ReviewJobResponse(job_id=job_id, status="queued")


@app.get("/api/review/job/{job_id}")
def get_job_status(job_id: str):
    """검수 Job 진행 상태 조회"""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ═══════════════════════════════════════════
# 리뷰 결과 조회
# ═══════════════════════════════════════════
@app.get("/api/reviews/{campaign_name}")
def api_list_reviews(campaign_name: str, limit: int = 200):
    return list_reviews(campaign_name, limit)


@app.get("/api/reviews/{campaign_name}/status")
def api_submission_status(campaign_name: str):
    """캠페인별 크리에이터 최신 검수 현황"""
    return get_submission_status(campaign_name)


@app.get("/api/reviews/{campaign_name}/{creator_name}")
def api_creator_reviews(campaign_name: str, creator_name: str):
    return get_creator_reviews(campaign_name, creator_name)


@app.get("/api/review/{review_id}")
def api_get_review(review_id: int):
    report = load_review(review_id)
    if not report:
        raise HTTPException(404, "Review not found")
    return report.model_dump()


# ═══════════════════════════════════════════
# 어드민 액션
# ═══════════════════════════════════════════
class AdminDecisionRequest(BaseModel):
    decision: str  # approved / revision_needed / rejected
    memo: Optional[str] = None


@app.post("/api/review/{review_id}/decision")
def api_admin_decision(review_id: int, body: AdminDecisionRequest):
    save_admin_decision(review_id, body.decision, body.memo)
    return {"ok": True}


class BrandFeedbackRequest(BaseModel):
    feedback: str
    set_revision: bool = True


@app.post("/api/review/{review_id}/brand-feedback")
def api_brand_feedback(review_id: int, body: BrandFeedbackRequest):
    save_brand_feedback(review_id, body.feedback, body.set_revision)
    return {"ok": True}


# ═══════════════════════════════════════════
# 캠페인 요약
# ═══════════════════════════════════════════
@app.get("/api/campaigns/summary")
def api_campaigns_summary():
    return get_campaigns_summary()


# ═══════════════════════════════════════════
# 파이프라인 (Drive 폴링 → 검수 → 시트 → 슬랙)
# ═══════════════════════════════════════════
@app.post("/api/pipeline/run")
async def trigger_pipeline(background_tasks: BackgroundTasks):
    """파이프라인 1회 실행 트리거"""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "progress": "파이프라인 시작 대기"}

    def _run():
        jobs[job_id]["status"] = "processing"
        try:
            from pipeline.main import run_once
            run_once()
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = {"message": "파이프라인 실행 완료"}
        except Exception as e:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)

    background_tasks.add_task(_run)
    return {"job_id": job_id, "status": "queued"}


# ═══════════════════════════════════════════
# 콘텐츠 검수 (Unpaid 캠페인)
# ═══════════════════════════════════════════
class ContentCheckRequest(BaseModel):
    url: str
    gl_id: str  # guidelines 테이블의 UUID

@app.post("/api/content-check")
async def check_content_endpoint(req: ContentCheckRequest):
    """Check posted content for unpaid campaigns (image/dedicated/unboxing/caption)."""
    guideline = load_guideline(req.gl_id)
    if not guideline:
        raise HTTPException(404, f"가이드라인을 찾을 수 없습니다 (gl_id={req.gl_id})")
    raw = check_content(req.url, guideline)
    # 프론트 호환 형식으로 매핑
    checks = []
    for c in raw.get("content_checks", []):
        checks.append({
            "name": c["check"].replace("_", " ").title(),
            "passed": c["status"] == "pass",
            "message": c["detail"],
        })
    caption = raw.get("caption_check", {})
    for item in caption.get("checks", []):
        checks.append({
            "name": item["element"],
            "passed": item["status"] == "found",
            "message": item["detail"],
        })
    return {"passed": raw["all_passed"], "checks": checks}


# ═══════════════════════════════════════════
# 캡션 검수 (Paid 캠페인)
# ═══════════════════════════════════════════
@app.post("/api/caption-check")
async def caption_check_endpoint(req: ContentCheckRequest):
    """Check caption/hashtags for paid campaigns after content submission."""
    guideline = load_guideline(req.gl_id)
    if not guideline:
        raise HTTPException(404, f"가이드라인을 찾을 수 없습니다 (gl_id={req.gl_id})")
    _platform, post_content = fetch_post_content(req.url)
    raw = check_upload(post_content, guideline)
    # 프론트 호환 형식으로 매핑
    results = []
    for item in raw.get("checks", []):
        results.append({
            "item": item["element"],
            "found": item["status"] == "found",
        })
    return {"passed": raw["all_passed"], "results": results}

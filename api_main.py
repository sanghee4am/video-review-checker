"""
Video Review Checker — FastAPI Backend
기존 Streamlit 검수 로직을 그대로 재활용, API로만 노출
"""
import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── 기존 모듈 그대로 import ──
from db import (
    save_guideline, list_guidelines, load_guideline, load_guideline_by_name,
    delete_guideline, save_review, list_reviews, load_review,
    get_previous_review, get_next_round, get_submission_status,
    get_creator_reviews, save_admin_decision, save_brand_feedback,
    get_latest_brand_feedback, get_campaigns_summary,
)
from models.guideline import ParsedGuideline
from models.review_result import ReviewReport
from processors.video_processor import process_video
from processors.guideline_parser import parse_guideline
from analyzer.compliance_checker import run_compliance_check
from pipeline.video_reviewer import run_pipeline_review


# ── 진행 상태 저장 (in-memory) ──
jobs: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    guideline_id: int
    campaign_name: str
    guideline: dict


@app.post("/api/guidelines/upload", response_model=GuidelineUploadResult)
async def upload_guideline(
    campaign_name: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """가이드라인 파일 업로드 → 파싱 → DB 저장"""
    file_items: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read()
        file_items.append((f.filename or "file", data))

    parsed, _images = parse_guideline(file_items)
    gid = save_guideline(campaign_name, parsed)
    return GuidelineUploadResult(
        guideline_id=gid,
        campaign_name=campaign_name,
        guideline=parsed.model_dump(),
    )


@app.get("/api/guidelines")
def api_list_guidelines():
    """저장된 가이드라인 목록"""
    return list_guidelines()


@app.get("/api/guidelines/{guideline_id}")
def api_get_guideline(guideline_id: int):
    result = load_guideline(guideline_id)
    if not result:
        raise HTTPException(404, "Guideline not found")
    campaign_name, parsed = result
    return {"campaign_name": campaign_name, "guideline": parsed.model_dump()}


@app.get("/api/guidelines/by-name/{campaign_name}")
def api_get_guideline_by_name(campaign_name: str):
    result = load_guideline_by_name(campaign_name)
    if not result:
        raise HTTPException(404, "Guideline not found")
    gid, parsed = result
    return {"guideline_id": gid, "guideline": parsed.model_dump()}


@app.delete("/api/guidelines/{guideline_id}")
def api_delete_guideline(guideline_id: int):
    delete_guideline(guideline_id)
    return {"ok": True}


# ═══════════════════════════════════════════
# 영상 검수 (비동기 Job)
# ═══════════════════════════════════════════
class ReviewJobRequest(BaseModel):
    campaign_name: str
    creator_name: str
    guideline_name: Optional[str] = None  # None이면 campaign_name으로 조회


class ReviewJobResponse(BaseModel):
    job_id: str
    status: str


def _run_review_job(
    job_id: str,
    video_bytes: bytes,
    filename: str,
    campaign_name: str,
    creator_name: str,
    guideline_name: str,
):
    """백그라운드에서 검수 실행"""
    jobs[job_id]["status"] = "processing"
    jobs[job_id]["progress"] = "영상 처리 시작"
    try:
        def progress_cb(msg: str):
            jobs[job_id]["progress"] = msg

        # 가이드라인 로드
        gl_result = load_guideline_by_name(guideline_name)
        if not gl_result:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = f"가이드라인 '{guideline_name}' 을 찾을 수 없습니다"
            return

        _gid, guideline = gl_result

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
            campaign_id=None,
            video_url=None,
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
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.post("/api/review", response_model=ReviewJobResponse)
async def start_review(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    campaign_name: str = Form(...),
    creator_name: str = Form(...),
    guideline_name: Optional[str] = Form(None),
):
    """영상 업로드 → 백그라운드 검수 Job 시작"""
    job_id = str(uuid.uuid4())
    video_bytes = await video.read()
    gl_name = guideline_name or campaign_name

    jobs[job_id] = {"status": "queued", "progress": "대기 중"}
    background_tasks.add_task(
        _run_review_job, job_id, video_bytes, video.filename or "video.mp4",
        campaign_name, creator_name, gl_name,
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

"""AI 검수 래퍼 모듈.

기존 검수기(process_video + run_compliance_check + save_review)를
Streamlit 없이 파이프라인에서 직접 호출하는 모듈.
"""
from __future__ import annotations

import sys
import os

# video-review-checker 루트를 Python 경로에 추가
# pipeline/ 폴더는 루트의 하위 디렉토리이므로 sys.path에 루트 추가
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dataclasses import dataclass
from typing import Optional

from processors.video_processor import process_video
from analyzer.compliance_checker import run_compliance_check
from db import save_review, load_guideline_by_name, get_previous_review
from models.review_result import ReviewReport


@dataclass
class ReviewResult:
    """파이프라인용 검수 결과 요약."""
    report: ReviewReport
    review_id: int
    score: int
    status: str            # approved / auto_approved / revision_needed / rejected
    brand_comment: str     # N열에 기입할 코멘트
    manual_flags: list[str]
    is_auto_approved: bool


def run_pipeline_review(
    video_bytes: bytes,
    filename: str,
    campaign_name: str,
    tiktok_handle: str,
    guideline_name: str,
) -> ReviewResult:
    """영상 bytes → AI 검수 → DB 저장 → 결과 반환.

    Args:
        video_bytes:    영상 원본 bytes
        filename:       파일명 (확장자 포함)
        campaign_name:  캠페인명 (예: "Magis Lene")
        tiktok_handle:  틱톡 핸들 (@없이, 예: "lisasvoging")
        guideline_name: vc_guidelines의 campaign_name (보통 캠페인명과 동일)

    Returns:
        ReviewResult

    Raises:
        ValueError: 가이드라인 없을 때
        RuntimeError: 영상 처리 실패 시
    """
    # 1. 가이드라인 로드
    guideline_result = load_guideline_by_name(guideline_name)
    if guideline_result is None:
        raise ValueError(
            f"가이드라인 없음: '{guideline_name}' — "
            f"어드민에서 먼저 가이드라인을 등록해주세요."
        )
    _guideline_id, guideline = guideline_result

    # 2. 이전 검수 이력 조회 (재검수 시 비교용)
    previous_result = get_previous_review(campaign_name, tiktok_handle)
    previous_report: Optional[ReviewReport] = None
    review_round = 1
    if previous_result:
        previous_report, prev_round = previous_result
        review_round = prev_round + 1
        print(
            f"[video_reviewer] @{tiktok_handle} 재검수 감지 "
            f"(이전 라운드: {prev_round}, 이번: {review_round})"
        )

    # 3. 영상 전처리 (프레임 추출 + Whisper STT)
    print(f"[video_reviewer] 영상 전처리 시작: {filename}")
    processed_video = process_video(video_bytes, filename)
    print(
        f"[video_reviewer] 전처리 완료: "
        f"{len(processed_video.frames)}프레임, "
        f"{'자막 있음' if processed_video.transcript else '자막 없음'}"
    )

    # 4. AI 검수 실행 (progress_callback 없이 headless 실행)
    print(f"[video_reviewer] AI 검수 시작: @{tiktok_handle} (라운드 {review_round})")
    report: ReviewReport = run_compliance_check(
        guideline=guideline,
        guideline_images=[],          # 파이프라인에서는 가이드라인 이미지 미사용
        video=processed_video,
        progress_callback=None,       # headless 모드 — 진행바 없음
        memo="",
        brand_feedback="",            # 파이프라인 1차 검수엔 피드백 없음
        previous_report=previous_report,
        review_round=review_round,
    )
    print(
        f"[video_reviewer] 검수 완료: "
        f"점수={report.overall_score}, 상태={report.overall_status}"
    )

    # 5. DB 저장
    review_id = save_review(
        campaign_name=campaign_name,
        creator_name=tiktok_handle,
        report=report,
        round_num=review_round,
    )
    print(f"[video_reviewer] DB 저장 완료: review_id={review_id}")

    # 6. 자동승인 여부
    is_auto_approved = (
        report.overall_score >= 90
        and not report.manual_review_flags
    )
    final_status = "auto_approved" if is_auto_approved else report.overall_status

    return ReviewResult(
        report=report,
        review_id=review_id,
        score=report.overall_score,
        status=final_status,
        brand_comment=report.brand_sheet_comment or "",
        manual_flags=report.manual_review_flags or [],
        is_auto_approved=is_auto_approved,
    )

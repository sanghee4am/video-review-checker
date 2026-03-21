"""파이프라인 메인 오케스트레이터.

실행 방법:
    python -m pipeline.main          # 한 번만 실행 (cron 방식)
    python -m pipeline.main --loop   # 5분 간격 루프 실행

흐름:
    Gmail 폴링
    → 영상/드라이브링크 추출
    → Google Drive 저장
    → 시트 M열(1st Draft) 기입
    → AI 검수 (process_video + run_compliance_check)
    → 시트 N열(새벽네시 코멘트) 기입
    → Slack 알림
    → 처리 완료 메일 ID 기록
"""
from __future__ import annotations

import argparse
import time
import traceback

from pipeline.config_pipeline import (
    CAMPAIGN_CONFIGS,
    POLL_INTERVAL_SECONDS,
)
from pipeline.gmail_watcher import poll_new_mails, mark_processed, IncomingMail
from pipeline.drive_handler import upload_bytes, copy_from_link
from pipeline.sheet_updater import write_draft_link, write_review_comment
from pipeline.slack_notifier import notify_review_complete, notify_error
from pipeline.video_reviewer import run_pipeline_review


def _get_sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}"


def _process_mail(mail: IncomingMail) -> None:
    """메일 1건 처리."""
    campaign_name = mail.campaign_name
    tiktok_handle = mail.tiktok_handle

    # 1. 캠페인 설정 확인
    config = CAMPAIGN_CONFIGS.get(campaign_name)
    if config is None:
        print(
            f"[main] 알 수 없는 캠페인: '{campaign_name}' — "
            f"config_pipeline.py에 CAMPAIGN_CONFIGS 추가 필요"
        )
        return

    sheet_id = config["sheet_id"]
    sheet_tab = config["sheet_tab"]
    guideline_name = config["guideline_name"]
    sheet_url = _get_sheet_url(sheet_id)

    print(f"\n{'='*60}")
    print(f"[main] 처리 시작: [{campaign_name}] @{tiktok_handle}")
    print(f"{'='*60}")

    try:
        drive_url: str | None = None
        video_bytes: bytes | None = None
        filename: str = "video.mp4"

        # ── Step 1: 영상 확보 ──────────────────────────────────
        if mail.has_video:
            # 첨부파일 우선 처리 (여러 개면 첫 번째만)
            filename, file_bytes = mail.attachments[0]
            print(f"[main] 첨부파일 업로드: {filename}")
            drive_url = upload_bytes(
                file_bytes=file_bytes,
                filename=filename,
                campaign_name=campaign_name,
                tiktok_handle=tiktok_handle,
            )
            video_bytes = file_bytes

        elif mail.has_drive_link:
            # 드라이브 링크 → 지정 폴더로 복사 + bytes 다운로드
            src_url = mail.drive_links[0]
            print(f"[main] 드라이브 링크 복사: {src_url}")
            drive_url, video_bytes = copy_from_link(
                drive_url=src_url,
                campaign_name=campaign_name,
                tiktok_handle=tiktok_handle,
            )
            filename = f"{tiktok_handle}_video.mp4"

        else:
            # gmail_watcher에서 이미 필터링했지만 방어적으로 처리
            print(f"[main] 영상/링크 없음 — 스킵: @{tiktok_handle}")
            return

        # ── Step 2: M열(1st Draft)에 드라이브 링크 기입 ──────
        print(f"[main] M열 기입: @{tiktok_handle} → {drive_url}")
        write_draft_link(
            sheet_id=sheet_id,
            sheet_tab=sheet_tab,
            tiktok_handle=tiktok_handle,
            drive_url=drive_url,
        )

        # ── Step 3: AI 검수 ────────────────────────────────────
        print(f"[main] AI 검수 시작: @{tiktok_handle}")
        result = run_pipeline_review(
            video_bytes=video_bytes,
            filename=filename,
            campaign_name=campaign_name,
            tiktok_handle=tiktok_handle,
            guideline_name=guideline_name,
        )

        # ── Step 4: N열(새벽네시 코멘트)에 AI 검수 결과 기입 ─
        print(f"[main] N열 기입: @{tiktok_handle} (score={result.score})")
        write_review_comment(
            sheet_id=sheet_id,
            sheet_tab=sheet_tab,
            tiktok_handle=tiktok_handle,
            comment=result.brand_comment,
            score=result.score,
            status=result.status,
        )

        # ── Step 5: Slack 알림 ─────────────────────────────────
        print(f"[main] Slack 알림 발송: @{tiktok_handle}")
        notify_review_complete(
            campaign_name=campaign_name,
            tiktok_handle=tiktok_handle,
            score=result.score,
            status=result.status,
            sheet_url=sheet_url,
            manual_flags=result.manual_flags,
        )

        # ── Step 6: 처리 완료 기록 ─────────────────────────────
        mark_processed(mail.message_id)
        print(
            f"[main] ✅ 완료: @{tiktok_handle} "
            f"(score={result.score}, status={result.status})"
        )

    except ValueError as e:
        # 가이드라인 없음 등 설정 오류
        print(f"[main] 설정 오류: {e}")
        notify_error(campaign_name, tiktok_handle, str(e))
        mark_processed(mail.message_id)  # 재시도 방지

    except Exception as e:
        print(f"[main] 처리 실패: @{tiktok_handle}\n{traceback.format_exc()}")
        notify_error(campaign_name, tiktok_handle, str(e))
        # 처리 실패한 메일은 mark_processed 하지 않음 → 다음 폴링 시 재시도


def run_once() -> None:
    """Gmail 폴링 → 새 메일 일괄 처리 (1회)."""
    print("[main] Gmail 폴링 시작...")
    mails = poll_new_mails(max_results=20)

    if not mails:
        print("[main] 처리할 신규 메일 없음.")
        return

    print(f"[main] 신규 메일 {len(mails)}건 감지.")
    for mail in mails:
        _process_mail(mail)


def run_loop() -> None:
    """POLL_INTERVAL_SECONDS 간격으로 반복 실행."""
    print(f"[main] 루프 모드 시작 (간격: {POLL_INTERVAL_SECONDS}초)")
    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            print("\n[main] 종료")
            break
        except Exception:
            print(f"[main] 폴링 루프 오류:\n{traceback.format_exc()}")
        print(f"[main] {POLL_INTERVAL_SECONDS}초 대기...")
        time.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="영상 검수 자동화 파이프라인"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help=f"루프 실행 (기본: 1회 실행). 간격: {POLL_INTERVAL_SECONDS}초",
    )
    args = parser.parse_args()

    if args.loop:
        run_loop()
    else:
        run_once()


if __name__ == "__main__":
    main()

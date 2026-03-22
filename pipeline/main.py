"""파이프라인 메인 오케스트레이터.

실행 방법:
    python -m pipeline.main          # 드라이브 폴더 스캔 → 새 파일 처리 (1회)

흐름:
    Drive 1st/2nd Draft 폴더 스캔
    → 파일명에서 틱톡핸들 파싱 ({핸들}_{파일명}.확장자)
    → 파일 다운로드
    → 시트 M열(1st Draft) 기입
    → AI 검수 (process_video + run_compliance_check)
    → 시트 N열(새벽네시 코멘트) 기입
    → Slack 알림
    → 처리 완료 파일 ID 기록
"""
from __future__ import annotations

import traceback

from pipeline.config_pipeline import CAMPAIGN_CONFIGS
from pipeline.drive_poller import scan_all_campaigns, download_file, mark_processed, DriveFile
from pipeline.sheet_updater import write_draft_link, write_review_comment
from pipeline.slack_notifier import notify_review_complete, notify_error
from pipeline.video_reviewer import run_pipeline_review
from pipeline.drive_handler import _make_shareable_link


def _get_sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}"


def _process_file(drive_file: DriveFile) -> None:
    """드라이브 파일 1건 처리."""
    campaign_name = drive_file.campaign_name
    tiktok_handle = drive_file.tiktok_handle
    filename = drive_file.filename
    draft_round = drive_file.draft_round

    config = CAMPAIGN_CONFIGS.get(campaign_name)
    if config is None:
        print(f"[main] 알 수 없는 캠페인: '{campaign_name}'")
        return

    sheet_id = config["sheet_id"]
    sheet_tab = config["sheet_tab"]
    guideline_name = config["guideline_name"]
    sheet_url = _get_sheet_url(sheet_id)

    print(f"\n{'='*60}")
    print(f"[main] 처리 시작: [{campaign_name}] @{tiktok_handle} ({filename}, {draft_round}차)")
    print(f"{'='*60}")

    try:
        # ── Step 1: 파일 다운로드 ──────────────────────────────
        print(f"[main] 파일 다운로드: {filename}")
        video_bytes = download_file(drive_file.file_id)
        drive_url = _make_shareable_link(drive_file.file_id)

        # ── Step 2: M열(1st/2nd Draft)에 드라이브 링크 기입 ──
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
        mark_processed(drive_file.file_id)
        print(
            f"[main] ✅ 완료: @{tiktok_handle} "
            f"(score={result.score}, status={result.status})"
        )

    except ValueError as e:
        print(f"[main] 설정 오류: {e}")
        notify_error(campaign_name, tiktok_handle, str(e))
        mark_processed(drive_file.file_id)  # 재시도 방지

    except Exception as e:
        print(f"[main] 처리 실패: @{tiktok_handle}\n{traceback.format_exc()}")
        notify_error(campaign_name, tiktok_handle, str(e))
        # 실패한 파일은 mark_processed 하지 않음 → 다음 실행 시 재시도


def run_once() -> None:
    """Drive 폴더 스캔 → 새 파일 일괄 처리 (1회)."""
    print("[main] Drive 폴더 스캔 시작...")
    files = scan_all_campaigns()

    if not files:
        print("[main] 처리할 새 파일 없음.")
        return

    print(f"[main] 신규 파일 {len(files)}건 감지.")
    for drive_file in files:
        _process_file(drive_file)


def main() -> None:
    run_once()


if __name__ == "__main__":
    main()

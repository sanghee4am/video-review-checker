"""Google Drive 폴더 폴링 모듈.

1st/2nd Draft 폴더를 스캔해서 새 파일 감지.
파일명 규칙: {틱톡핸들}_{파일명}.mp4
예: lucyhan_draft1.mp4, nipzreal_video.mov

처리 흐름:
1. 1st/2nd Draft 폴더 스캔
2. 파일명에서 틱톡핸들 파싱
3. 이미 처리된 파일 ID는 스킵 (중복 방지)
4. 새 파일 bytes 다운로드 + 처리 정보 반환
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from googleapiclient.http import MediaIoBaseDownload

from pipeline.config_pipeline import (
    CAMPAIGN_CONFIGS,
    PROCESSED_IDS_PATH,
)
from pipeline.drive_handler import _get_drive_service

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".MOV"}


class DriveFile:
    """드라이브에서 감지된 파일 정보."""
    def __init__(
        self,
        file_id: str,
        filename: str,
        tiktok_handle: str,
        campaign_name: str,
        draft_round: int,           # 1 or 2
        folder_id: str,
    ):
        self.file_id = file_id
        self.filename = filename
        self.tiktok_handle = tiktok_handle
        self.campaign_name = campaign_name
        self.draft_round = draft_round
        self.folder_id = folder_id

    def __repr__(self):
        return (
            f"DriveFile(campaign={self.campaign_name!r}, "
            f"creator={self.tiktok_handle!r}, "
            f"file={self.filename!r}, "
            f"round={self.draft_round})"
        )


def _load_processed_ids() -> set[str]:
    """처리 완료된 파일 ID 로드."""
    path = Path(PROCESSED_IDS_PATH)
    if not path.exists():
        return set()
    return set(path.read_text().strip().splitlines())


def _save_processed_id(file_id: str) -> None:
    """처리 완료된 파일 ID 저장."""
    path = Path(PROCESSED_IDS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(file_id + "\n")


def _parse_handle_from_filename(filename: str) -> str | None:
    """파일명에서 틱톡핸들 추출.

    규칙: {핸들}_{나머지파일명}.확장자
    예: lucyhan_draft1.mp4 → lucyhan
        nipzreal07_video.MOV → nipzreal07
    """
    stem = Path(filename).stem  # 확장자 제외
    if "_" not in stem:
        return None
    handle = stem.split("_")[0]
    return handle if handle else None


def _scan_folder(
    service,
    folder_id: str,
    campaign_name: str,
    draft_round: int,
    processed_ids: set[str],
) -> list[DriveFile]:
    """폴더 내 새 영상 파일 스캔."""
    results = []

    try:
        response = service.files().list(
            q=(
                f"'{folder_id}' in parents "
                f"and trashed = false "
                f"and mimeType contains 'video/'"
            ),
            fields="files(id, name, mimeType, createdTime)",
            orderBy="createdTime desc",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
    except Exception as e:
        print(f"[drive_poller] 폴더 스캔 실패 ({folder_id}): {e}")
        return []

    for f in response.get("files", []):
        file_id = f["id"]
        filename = f["name"]
        ext = Path(filename).suffix

        # 영상 파일만
        if ext.lower() not in {e.lower() for e in VIDEO_EXTENSIONS}:
            continue

        # 이미 처리된 파일 스킵
        if file_id in processed_ids:
            continue

        # 파일명에서 핸들 파싱
        handle = _parse_handle_from_filename(filename)
        if not handle:
            print(
                f"[drive_poller] 파일명 규칙 불일치 (핸들 추출 불가): {filename!r} — "
                f"규칙: {{핸들}}_{{파일명}}.mp4"
            )
            continue

        drive_file = DriveFile(
            file_id=file_id,
            filename=filename,
            tiktok_handle=handle,
            campaign_name=campaign_name,
            draft_round=draft_round,
            folder_id=folder_id,
        )
        results.append(drive_file)
        print(f"[drive_poller] 신규 파일 감지: {drive_file}")

    return results


def scan_all_campaigns() -> list[DriveFile]:
    """모든 캠페인의 1st/2nd Draft 폴더 스캔.

    Returns: 미처리 새 파일 목록
    """
    processed_ids = _load_processed_ids()
    service = _get_drive_service()
    all_files: list[DriveFile] = []

    for campaign_name, config in CAMPAIGN_CONFIGS.items():
        folder_1st = config.get("drive_folder_1st")
        folder_2nd = config.get("drive_folder_2nd")

        if folder_1st:
            files = _scan_folder(
                service, folder_1st, campaign_name, 1, processed_ids
            )
            all_files.extend(files)

        if folder_2nd:
            files = _scan_folder(
                service, folder_2nd, campaign_name, 2, processed_ids
            )
            all_files.extend(files)

    return all_files


def download_file(file_id: str) -> bytes:
    """드라이브 파일 bytes 다운로드."""
    service = _get_drive_service()
    request = service.files().get_media(
        fileId=file_id,
        supportsAllDrives=True,
    )
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def mark_processed(file_id: str) -> None:
    """파일 처리 완료 표시."""
    _save_processed_id(file_id)

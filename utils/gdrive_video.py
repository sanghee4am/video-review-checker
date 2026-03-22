from __future__ import annotations

import io
import json
import re
import tempfile
from pathlib import Path

import gdown


def extract_gdrive_file_id(url: str) -> str | None:
    """Extract file ID from various Google Drive URL formats."""
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"open\?id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


def is_gdrive_url(url: str) -> bool:
    """Check if URL is a Google Drive link."""
    return "drive.google.com" in url.lower()


def _get_drive_service():
    """서비스 계정 기반 Drive API 서비스 객체 반환."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        # Streamlit secrets에서 서비스 계정 JSON 로드
        try:
            import streamlit as st
            sa_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        except Exception:
            # 로컬: 환경변수 또는 파일에서 로드
            import os
            sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "")
            if sa_path and Path(sa_path).exists():
                sa_info = json.loads(Path(sa_path).read_text())
            else:
                return None

        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        return build("drive", "v3", credentials=creds)
    except Exception:
        return None


def _download_via_api(file_id: str, tmp_path: Path) -> str | None:
    """Drive API로 파일 다운로드. 성공 시 파일명 반환, 실패 시 예외."""
    from googleapiclient.http import MediaIoBaseDownload

    service = _get_drive_service()
    if not service:
        raise RuntimeError("Drive 서비스 계정 인증 실패 (GOOGLE_SERVICE_ACCOUNT 시크릿 확인)")

    file_info = service.files().get(
        fileId=file_id, fields="name"
    ).execute()

    request = service.files().get_media(fileId=file_id)
    with open(tmp_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    return file_info.get("name", f"video_{file_id}.mp4")


def download_gdrive_video(url: str, progress_callback=None) -> tuple[str, Path]:
    """Download a video file from Google Drive.

    서비스 계정 Drive API 우선 시도, 실패 시 gdown 폴백.
    """
    file_id = extract_gdrive_file_id(url)
    if not file_id:
        raise ValueError(
            "Google Drive 파일 ID를 URL에서 찾을 수 없습니다.\n"
            "파일 링크를 확인해주세요. (예: https://drive.google.com/file/d/xxxxx/view)"
        )

    tmp_path = Path(tempfile.mktemp(suffix=".mp4"))

    if progress_callback:
        progress_callback(0, None)

    # 1) 서비스 계정 Drive API로 시도 (공개 설정 불필요)
    api_error = None
    try:
        filename = _download_via_api(file_id, tmp_path)
    except Exception as e:
        filename = None
        api_error = e
    if filename and tmp_path.exists() and tmp_path.stat().st_size > 1000:
        if progress_callback:
            mb = tmp_path.stat().st_size / (1024 * 1024)
            progress_callback(mb, mb)
        return filename, tmp_path

    # API 실패 시 원인 출력 후 gdown 폴백
    if api_error:
        print(f"[gdrive] Drive API 실패: {api_error}")
    else:
        print(f"[gdrive] Drive API: filename={filename}, exists={tmp_path.exists()}, size={tmp_path.stat().st_size if tmp_path.exists() else 0}")
    tmp_path.unlink(missing_ok=True)
    tmp_path = Path(tempfile.mktemp(suffix=".mp4"))

    # 2) gdown 폴백 (공개 링크만 가능)
    try:
        output = gdown.download(
            id=file_id,
            output=str(tmp_path),
            quiet=False,
            fuzzy=True,
        )

        if output is None or not tmp_path.exists():
            raise ValueError(
                "Google Drive에서 파일을 다운로드할 수 없습니다.\n"
                "파일이 '링크가 있는 모든 사람' 공유 설정인지 확인해주세요.\n"
                "또는 파일이 삭제/이동되었을 수 있습니다."
            )

        file_size = tmp_path.stat().st_size
        if file_size < 1000:
            tmp_path.unlink(missing_ok=True)
            raise ValueError(
                "다운로드된 파일이 너무 작습니다. 파일 링크를 확인해주세요.\n"
                "파일이 공유 설정되어 있는지, 또는 링크가 올바른지 확인해주세요."
            )

        if progress_callback:
            mb = file_size / (1024 * 1024)
            progress_callback(mb, mb)

        filename = Path(output).name if output else f"video_{file_id}.mp4"
        return filename, tmp_path

    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        if "ValueError" in type(e).__name__:
            raise
        raise ValueError(
            f"Google Drive 다운로드 실패: {e}\n"
            "파일이 '링크가 있는 모든 사람' 공유 설정인지 확인해주세요."
        )

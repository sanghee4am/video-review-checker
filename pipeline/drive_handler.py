"""Google Drive 파일 업로드 모듈.

메일 첨부 영상 또는 드라이브 원본 링크를
지정된 드라이브 폴더에 저장하고 공유 링크 반환.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

from pipeline.config_pipeline import (
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_TOKEN_PATH,
    DRIVE_FOLDER_ID,
)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
]


def _get_drive_service():
    """Drive API 서비스 객체 반환."""
    token_path = GOOGLE_TOKEN_PATH.replace(".json", "_drive.json")
    creds = None

    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def _make_shareable_link(file_id: str) -> str:
    """드라이브 파일 공유 링크 생성."""
    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"


def _extract_file_id(drive_url: str) -> str | None:
    """드라이브 URL에서 파일 ID 추출."""
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"open\?id=([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, drive_url)
        if match:
            return match.group(1)
    return None


def upload_bytes(
    file_bytes: bytes,
    filename: str,
    campaign_name: str,
    tiktok_handle: str,
    folder_id: str = DRIVE_FOLDER_ID,
) -> str:
    """영상 bytes를 드라이브에 업로드.

    캠페인명/틱톡핸들 기반으로 파일명 정리:
    예: MagisLene_lisasvoging_1st.mp4

    Returns: 공유 링크 URL
    """
    service = _get_drive_service()

    # 파일명 정규화
    safe_campaign = re.sub(r"[^\w]", "", campaign_name.replace(" ", ""))
    clean_filename = f"{safe_campaign}_{tiktok_handle}_{filename}"

    # 캠페인별 서브폴더 생성 또는 조회
    subfolder_id = _get_or_create_subfolder(service, campaign_name, folder_id)

    # 업로드
    ext = Path(filename).suffix.lower()
    mime_map = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".m4v": "video/x-m4v",
    }
    mime_type = mime_map.get(ext, "video/mp4")

    file_metadata = {
        "name": clean_filename,
        "parents": [subfolder_id],
    }
    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes),
        mimetype=mime_type,
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name",
    ).execute()

    file_id = uploaded["id"]
    print(f"[drive_handler] 업로드 완료: {clean_filename} (id={file_id})")

    # 링크 공개 권한 설정 (뷰어)
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return _make_shareable_link(file_id)


def copy_from_link(
    drive_url: str,
    campaign_name: str,
    tiktok_handle: str,
    folder_id: str = DRIVE_FOLDER_ID,
) -> tuple[str, bytes]:
    """기존 드라이브 링크의 파일을 지정 폴더로 복사.

    Returns: (공유 링크 URL, 파일 bytes)
    """
    service = _get_drive_service()

    file_id = _extract_file_id(drive_url)
    if not file_id:
        raise ValueError(f"드라이브 링크에서 파일 ID를 추출할 수 없음: {drive_url}")

    # 원본 파일 정보 조회
    file_info = service.files().get(
        fileId=file_id,
        fields="name, mimeType",
    ).execute()
    original_name = file_info["name"]

    # 캠페인별 서브폴더
    subfolder_id = _get_or_create_subfolder(service, campaign_name, folder_id)

    # 파일명 정규화
    safe_campaign = re.sub(r"[^\w]", "", campaign_name.replace(" ", ""))
    new_name = f"{safe_campaign}_{tiktok_handle}_{original_name}"

    # 복사
    copied = service.files().copy(
        fileId=file_id,
        body={
            "name": new_name,
            "parents": [subfolder_id],
        },
        fields="id",
    ).execute()

    new_file_id = copied["id"]

    # 공개 권한
    service.permissions().create(
        fileId=new_file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    # 파일 bytes 다운로드 (검수용)
    file_bytes = _download_bytes(service, new_file_id)

    share_url = _make_shareable_link(new_file_id)
    print(f"[drive_handler] 복사 완료: {new_name} → {share_url}")

    return share_url, file_bytes


def download_for_review(drive_url: str) -> tuple[str, bytes]:
    """드라이브 링크에서 파일 bytes 다운로드 (검수용).

    Returns: (파일명, bytes)
    """
    service = _get_drive_service()

    file_id = _extract_file_id(drive_url)
    if not file_id:
        raise ValueError(f"드라이브 파일 ID 추출 실패: {drive_url}")

    file_info = service.files().get(
        fileId=file_id,
        fields="name",
    ).execute()

    file_bytes = _download_bytes(service, file_id)
    return file_info["name"], file_bytes


def _download_bytes(service, file_id: str) -> bytes:
    """드라이브 파일 bytes 다운로드."""
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _get_or_create_subfolder(service, folder_name: str, parent_id: str) -> str:
    """캠페인명으로 서브폴더 조회 또는 생성. folder ID 반환."""
    # 기존 폴더 조회
    query = (
        f"name = '{folder_name}' "
        f"and '{parent_id}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    result = service.files().list(
        q=query,
        fields="files(id, name)",
    ).execute()

    files = result.get("files", [])
    if files:
        return files[0]["id"]

    # 없으면 생성
    folder = service.files().create(
        body={
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        fields="id",
    ).execute()
    print(f"[drive_handler] 서브폴더 생성: {folder_name}")
    return folder["id"]

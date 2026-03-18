from __future__ import annotations

import re
import tempfile
from pathlib import Path

import requests


def extract_gdrive_file_id(url: str) -> str | None:
    """Extract file ID from various Google Drive URL formats."""
    # /file/d/FILE_ID/
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    # ?id=FILE_ID
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    # /open?id=FILE_ID
    match = re.search(r"open\?id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


def is_gdrive_url(url: str) -> bool:
    """Check if URL is a Google Drive link."""
    return "drive.google.com" in url.lower()


def download_gdrive_video(url: str, progress_callback=None) -> tuple[str, Path]:
    """Download a video file from Google Drive.

    Handles the large file virus scan confirmation page automatically.

    Args:
        url: Google Drive file URL
        progress_callback: Optional callback(downloaded_mb, total_mb_or_none)

    Returns:
        (original_filename, temp_file_path)

    Raises:
        ValueError if download fails.
    """
    file_id = extract_gdrive_file_id(url)
    if not file_id:
        raise ValueError(
            "Google Drive 파일 ID를 URL에서 찾을 수 없습니다.\n"
            "파일 링크를 확인해주세요. (예: https://drive.google.com/file/d/xxxxx/view)"
        )

    # Step 1: Initial request to get download or confirmation page
    session = requests.Session()
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    resp = session.get(download_url, stream=True, timeout=30)
    if resp.status_code != 200:
        raise ValueError(
            f"Google Drive 접근 실패 (HTTP {resp.status_code}).\n"
            "파일이 '링크가 있는 모든 사람' 공유 설정인지 확인해주세요."
        )

    # Check if we got a virus scan confirmation page (for large files)
    confirm_token = None
    for key, value in resp.cookies.items():
        if key.startswith("download_warning"):
            confirm_token = value
            break

    if not confirm_token:
        # Check in response text for confirmation token
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            text = resp.text
            match = re.search(r'confirm=([0-9A-Za-z_-]+)', text)
            if match:
                confirm_token = match.group(1)
            else:
                # Try uuid pattern
                match = re.search(r'id="downloadForm".*?action="(.*?)"', text, re.DOTALL)
                if match:
                    download_url = match.group(1).replace("&amp;", "&")
                    confirm_token = "t"

    if confirm_token:
        download_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
        resp = session.get(download_url, stream=True, timeout=30)

    # Detect filename from Content-Disposition header
    filename = f"video_{file_id}.mp4"
    cd = resp.headers.get("Content-Disposition", "")
    if cd:
        fn_match = re.search(r"filename\*?=['\"]?(?:UTF-8'')?([^;'\"]+)", cd)
        if fn_match:
            filename = requests.utils.unquote(fn_match.group(1).strip('"'))

    # Get total size if available
    total_size = None
    content_length = resp.headers.get("Content-Length")
    if content_length:
        total_size = int(content_length)

    # Verify it's actually a video/binary file, not an HTML error page
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type and total_size and total_size < 100000:
        raise ValueError(
            "Google Drive에서 영상 파일을 다운로드할 수 없습니다.\n"
            "파일이 '링크가 있는 모든 사람' 공유 설정인지 확인해주세요.\n"
            "또는 파일이 삭제/이동되었을 수 있습니다."
        )

    # Download to temp file
    suffix = Path(filename).suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    downloaded = 0
    chunk_size = 1024 * 1024  # 1MB chunks

    for chunk in resp.iter_content(chunk_size=chunk_size):
        if chunk:
            tmp.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                dl_mb = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024) if total_size else None
                progress_callback(dl_mb, total_mb)

    tmp.close()

    if downloaded < 1000:
        Path(tmp.name).unlink(missing_ok=True)
        raise ValueError(
            "다운로드된 파일이 너무 작습니다. 파일 링크를 확인해주세요.\n"
            "파일이 공유 설정되어 있는지, 또는 링크가 올바른지 확인해주세요."
        )

    return filename, Path(tmp.name)

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import gdown


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
    """Download a video file from Google Drive using gdown.

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

    # Create temp file
    tmp_path = Path(tempfile.mktemp(suffix=".mp4"))

    try:
        if progress_callback:
            progress_callback(0, None)

        # gdown handles large files, virus scan confirmations, etc.
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

        # Try to get original filename from gdown output
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

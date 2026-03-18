from __future__ import annotations

import re
import io
import requests
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs


def detect_url_type(url: str) -> Optional[str]:
    """Detect the type of URL: 'gdrive', 'gsheets', 'gslides', 'notion', or None."""
    if "docs.google.com/spreadsheets" in url:
        return "gsheets"
    if "docs.google.com/presentation" in url:
        return "gslides"
    if "drive.google.com" in url:
        return "gdrive"
    if "notion.site" in url or "notion.so" in url:
        return "notion"
    return None


def _extract_gdrive_file_id(url: str) -> Optional[str]:
    """Extract file ID from various Google Drive URL formats."""
    # Format: /file/d/FILE_ID/
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    # Format: ?id=FILE_ID
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


def _extract_gsheets_id(url: str) -> Optional[str]:
    """Extract spreadsheet ID from Google Sheets URL."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def _extract_gslides_id(url: str) -> Optional[str]:
    """Extract presentation ID from Google Slides URL."""
    match = re.search(r"/presentation/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def _extract_gsheets_gid(url: str) -> Optional[str]:
    """Extract gid (sheet ID) from Google Sheets URL."""
    match = re.search(r"gid=(\d+)", url)
    return match.group(1) if match else "0"


def fetch_from_url(url: str) -> Tuple[str, bytes]:
    """Fetch guideline content from a URL.

    Returns:
        (filename, file_bytes) tuple

    Raises:
        ValueError if URL type is unsupported or fetch fails.
    """
    url_type = detect_url_type(url)

    if url_type == "gdrive":
        return _fetch_gdrive(url)
    elif url_type == "gsheets":
        return _fetch_gsheets(url)
    elif url_type == "gslides":
        return _fetch_gslides(url)
    elif url_type == "notion":
        raise ValueError(
            "Notion 페이지는 직접 다운로드가 어렵습니다.\n"
            "Notion에서 PDF로 내보내기 후 파일을 업로드해주세요.\n"
            "(페이지 우측 상단 ··· → Export → PDF)"
        )
    else:
        # Try direct download
        return _fetch_direct(url)


def _fetch_gdrive(url: str) -> Tuple[str, bytes]:
    """Download file from Google Drive."""
    file_id = _extract_gdrive_file_id(url)
    if not file_id:
        raise ValueError("Google Drive 파일 ID를 URL에서 찾을 수 없습니다.")

    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    resp = requests.get(download_url, allow_redirects=True, timeout=30)

    if resp.status_code != 200:
        raise ValueError(f"Google Drive 다운로드 실패 (HTTP {resp.status_code}). 파일이 공개 설정인지 확인해주세요.")

    # Try to detect file type from content-type
    content_type = resp.headers.get("Content-Type", "")
    if "pdf" in content_type:
        ext = ".pdf"
    elif "spreadsheet" in content_type or "excel" in content_type:
        ext = ".xlsx"
    elif "png" in content_type:
        ext = ".png"
    elif "jpeg" in content_type or "jpg" in content_type:
        ext = ".jpg"
    else:
        ext = ".pdf"  # default assumption

    return f"gdrive_file{ext}", resp.content


def _fetch_gsheets(url: str) -> Tuple[str, bytes]:
    """Export Google Sheets as Excel file."""
    sheet_id = _extract_gsheets_id(url)
    if not sheet_id:
        raise ValueError("Google Sheets ID를 URL에서 찾을 수 없습니다.")

    # Export as xlsx
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    resp = requests.get(export_url, allow_redirects=True, timeout=30)

    if resp.status_code == 200 and len(resp.content) > 1000:
        return "spreadsheet.xlsx", resp.content

    # Fallback: try CSV via gviz
    gid = _extract_gsheets_gid(url)
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}"
    resp = requests.get(csv_url, allow_redirects=True, timeout=30)

    if resp.status_code != 200:
        raise ValueError("Google Sheets 다운로드 실패. 파일이 '링크가 있는 모든 사람' 공유 설정인지 확인해주세요.")

    # Save CSV content as text, will be handled as extra text in parser
    return "spreadsheet.csv", resp.content


def _fetch_gslides(url: str) -> Tuple[str, bytes]:
    """Export Google Slides as PDF."""
    slides_id = _extract_gslides_id(url)
    if not slides_id:
        raise ValueError("Google Slides ID를 URL에서 찾을 수 없습니다.")

    export_url = f"https://docs.google.com/presentation/d/{slides_id}/export/pdf"
    resp = requests.get(export_url, allow_redirects=True, timeout=30)

    if resp.status_code == 200 and len(resp.content) > 5000:
        return "slides.pdf", resp.content

    raise ValueError(
        "Google Slides PDF 다운로드 실패.\n"
        "슬라이드가 '링크가 있는 모든 사람' 공유 설정인지 확인하거나,\n"
        "직접 PDF로 다운로드 후 파일을 업로드해주세요.\n"
        "(파일 → 다운로드 → PDF)"
    )


def _fetch_direct(url: str) -> Tuple[str, bytes]:
    """Try direct download from URL."""
    try:
        resp = requests.get(url, allow_redirects=True, timeout=30)
        if resp.status_code != 200:
            raise ValueError(f"다운로드 실패 (HTTP {resp.status_code})")

        content_type = resp.headers.get("Content-Type", "")
        if "pdf" in content_type:
            return "downloaded.pdf", resp.content
        elif "image" in content_type:
            ext = ".png" if "png" in content_type else ".jpg"
            return f"downloaded{ext}", resp.content
        else:
            raise ValueError("지원하지 않는 파일 형식입니다. PDF, 이미지, Google Docs 링크를 사용해주세요.")
    except requests.RequestException as e:
        raise ValueError(f"URL 접근 실패: {e}")

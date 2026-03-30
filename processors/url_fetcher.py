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
        return _fetch_notion(url)
    else:
        # Try direct download
        return _fetch_direct(url)


def _extract_notion_page_id(url: str) -> Optional[str]:
    """Extract 32-char hex page ID from Notion URL and format as UUID."""
    # Try to find 32-char hex ID in the URL (with or without dashes)
    match = re.search(r"([a-f0-9]{32})", url.replace("-", ""))
    if not match:
        # Try UUID format directly
        match = re.search(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", url)
        if match:
            return match.group(1)
        return None
    pid = match.group(1)
    return f"{pid[:8]}-{pid[8:12]}-{pid[12:16]}-{pid[16:20]}-{pid[20:]}"


def _fetch_notion_blocks(page_id_uuid: str) -> list[dict]:
    """Fetch all blocks from a public Notion page via internal API."""
    all_blocks = {}
    cursor = {"stack": []}
    for chunk_num in range(10):  # max 10 chunks
        resp = requests.post(
            "https://www.notion.so/api/v3/loadPageChunk",
            json={
                "page": {"id": page_id_uuid},
                "limit": 200,
                "cursor": cursor,
                "chunkNumber": chunk_num,
                "verticalColumns": False,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        blocks = data.get("recordMap", {}).get("block", {})
        if not blocks:
            break
        all_blocks.update(blocks)
        cursor = data.get("cursor", {"stack": []})
        if not cursor.get("stack"):
            break
    return all_blocks


def _notion_blocks_to_markdown(blocks: dict) -> str:
    """Convert Notion blocks to markdown text."""
    lines = []
    for bid, bdata in blocks.items():
        val = bdata.get("value", {})
        btype = val.get("type", "")
        props = val.get("properties", {})
        title_parts = props.get("title", [])

        text = ""
        for part in title_parts:
            if isinstance(part, list) and len(part) > 0:
                text += str(part[0])

        if not text.strip():
            continue

        if btype == "page":
            lines.append(f"# {text}")
        elif btype == "header":
            lines.append(f"## {text}")
        elif btype == "sub_header":
            lines.append(f"### {text}")
        elif btype == "sub_sub_header":
            lines.append(f"#### {text}")
        elif btype == "bulleted_list":
            lines.append(f"- {text}")
        elif btype == "numbered_list":
            lines.append(f"1. {text}")
        elif btype == "to_do":
            checked = props.get("checked", [["No"]])[0][0]
            mark = "x" if checked == "Yes" else " "
            lines.append(f"- [{mark}] {text}")
        elif btype == "toggle":
            lines.append(f"▶ {text}")
        elif btype == "quote":
            lines.append(f"> {text}")
        elif btype == "callout":
            lines.append(f"📌 {text}")
        elif btype == "divider":
            lines.append("---")
        else:
            lines.append(text)
    return "\n".join(lines)


def _fetch_notion(url: str) -> Tuple[str, bytes]:
    """Fetch content from a public Notion page as markdown text (returned as CSV bytes for parser compatibility)."""
    page_id = _extract_notion_page_id(url)
    if not page_id:
        raise ValueError("Notion 페이지 ID를 URL에서 찾을 수 없습니다.")

    blocks = _fetch_notion_blocks(page_id)
    if not blocks:
        raise ValueError(
            "Notion 페이지 내용을 가져올 수 없습니다.\n"
            "페이지가 '웹에 게시(Publish to web)' 설정인지 확인해주세요."
        )

    markdown = _notion_blocks_to_markdown(blocks)
    if len(markdown.strip()) < 50:
        raise ValueError("Notion 페이지에서 충분한 텍스트를 추출하지 못했습니다.")

    return "notion_guideline.csv", markdown.encode("utf-8")


def fetch_notion_by_page_id(page_id_raw: str) -> Tuple[str, bytes]:
    """Fetch Notion page by raw page ID (32-char hex, no dashes). For direct use without URL."""
    pid = page_id_raw.replace("-", "")
    page_id_uuid = f"{pid[:8]}-{pid[8:12]}-{pid[12:16]}-{pid[16:20]}-{pid[20:]}"
    blocks = _fetch_notion_blocks(page_id_uuid)
    if not blocks:
        raise ValueError(
            f"Notion 페이지 내용을 가져올 수 없습니다 (page_id={page_id_raw}).\n"
            "페이지가 '웹에 게시' 설정인지 확인해주세요."
        )
    markdown = _notion_blocks_to_markdown(blocks)
    if len(markdown.strip()) < 50:
        raise ValueError("Notion 페이지에서 충분한 텍스트를 추출하지 못했습니다.")
    return "notion_guideline.csv", markdown.encode("utf-8")


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

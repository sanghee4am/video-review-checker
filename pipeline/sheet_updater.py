"""Google Sheets 업데이트 모듈.

캠페인 보드 시트의 M열(1st Draft), N열(새벽네시 코멘트) 자동 기입.
TikTok ID(C열)로 행을 찾아 해당 열에 값 기입.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from pipeline.config_pipeline import (
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_TOKEN_PATH,
    COL_TIKTOK_ID,
    COL_1ST_DRAFT,
    COL_COMMENT,
    COL_UPDATE_DATE,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# 컬럼 문자 → 숫자 인덱스 (A=1)
def _col_to_idx(col: str) -> int:
    col = col.upper()
    result = 0
    for c in col:
        result = result * 26 + (ord(c) - ord("A") + 1)
    return result


def _get_sheets_service():
    """Sheets API 서비스 객체 반환."""
    token_path = GOOGLE_TOKEN_PATH.replace(".json", "_sheets.json")
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

    return build("sheets", "v4", credentials=creds)


def _find_creator_row(
    service,
    sheet_id: str,
    sheet_tab: str,
    tiktok_handle: str,
) -> int | None:
    """C열(TikTok ID)에서 핸들 검색 → 행 번호 반환 (1-indexed).

    Returns None if not found.
    """
    range_name = f"'{sheet_tab}'!{COL_TIKTOK_ID}:{COL_TIKTOK_ID}"
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=range_name,
    ).execute()

    values = result.get("values", [])
    handle_lower = tiktok_handle.lower().strip().lstrip("@")

    for i, row in enumerate(values):
        if row and row[0].lower().strip().lstrip("@") == handle_lower:
            return i + 1  # 1-indexed

    return None


def write_draft_link(
    sheet_id: str,
    sheet_tab: str,
    tiktok_handle: str,
    drive_url: str,
) -> bool:
    """M열(1st Draft)에 드라이브 링크 기입.

    Returns True if successful, False if creator not found.
    """
    service = _get_sheets_service()
    row = _find_creator_row(service, sheet_id, sheet_tab, tiktok_handle)

    if row is None:
        print(f"[sheet_updater] 크리에이터 미발견: @{tiktok_handle}")
        return False

    # M열 업데이트
    range_name = f"'{sheet_tab}'!{COL_1ST_DRAFT}{row}"
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body={"values": [[drive_url]]},
    ).execute()

    # A열 날짜 업데이트
    date_range = f"'{sheet_tab}'!{COL_UPDATE_DATE}{row}"
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=date_range,
        valueInputOption="USER_ENTERED",
        body={"values": [[datetime.now().strftime("%Y-%m-%d")]]},
    ).execute()

    print(f"[sheet_updater] @{tiktok_handle} M열 기입 완료: {drive_url}")
    return True


def write_review_comment(
    sheet_id: str,
    sheet_tab: str,
    tiktok_handle: str,
    comment: str,
    score: int,
    status: str,
) -> bool:
    """N열(새벽네시 코멘트)에 AI 검수 결과 기입.

    comment: brand_sheet_comment (한국어)
    score: 검수 점수
    status: approved / revision_needed / rejected

    Returns True if successful.
    """
    service = _get_sheets_service()
    row = _find_creator_row(service, sheet_id, sheet_tab, tiktok_handle)

    if row is None:
        print(f"[sheet_updater] 크리에이터 미발견: @{tiktok_handle}")
        return False

    # 상태 이모지
    status_emoji = {
        "approved": "✅",
        "auto_approved": "✅",
        "revision_needed": "🔄",
        "rejected": "❌",
    }.get(status, "⏳")

    # N열에 기입할 내용: 점수 + 상태 + AI 코멘트
    cell_value = f"[AI검수 {score}점 {status_emoji}]\n{comment}"

    range_name = f"'{sheet_tab}'!{COL_COMMENT}{row}"
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body={"values": [[cell_value]]},
    ).execute()

    print(f"[sheet_updater] @{tiktok_handle} N열 기입 완료 (score={score}, status={status})")
    return True

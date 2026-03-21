"""Gmail 감시 모듈.

메일 제목 규칙: [캠페인명] @틱톡핸들 ...
예: [Magis Lene] @lisasvoging 1차 영상

처리 흐름:
1. Gmail API로 새 메일 폴링
2. 제목에서 캠페인명 + 틱톡핸들 파싱
3. 첨부파일(영상) or 본문의 드라이브 링크 추출
4. 처리 완료된 메일 ID 기록 (중복 방지)
"""
from __future__ import annotations

import base64
import os
import re
import io
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from pipeline.config_pipeline import (
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_TOKEN_PATH,
    SUBJECT_PATTERN,
    PROCESSED_IDS_PATH,
    GMAIL_ACCOUNTS,
)

# Gmail 읽기 + 첨부파일 다운로드 권한
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# 지원하는 영상 확장자
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

# 드라이브 링크 패턴
DRIVE_LINK_PATTERN = r"https://drive\.google\.com/(?:file/d/|open\?id=|drive/folders/)([a-zA-Z0-9_-]+)"


def _get_gmail_service(account_email: str):
    """Gmail API 서비스 객체 반환 (OAuth2 인증)."""
    token_path = GOOGLE_TOKEN_PATH.replace(".json", f"_{account_email.split('@')[0]}.json")
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

    return build("gmail", "v1", credentials=creds)


def _load_processed_ids() -> set[str]:
    """처리 완료된 메일 ID 로드."""
    path = Path(PROCESSED_IDS_PATH)
    if not path.exists():
        return set()
    return set(path.read_text().strip().splitlines())


def _save_processed_id(message_id: str) -> None:
    """처리 완료된 메일 ID 저장."""
    path = Path(PROCESSED_IDS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(message_id + "\n")


def _parse_subject(subject: str) -> Optional[tuple[str, str]]:
    """제목에서 (캠페인명, 틱톡핸들) 추출.

    Returns None if pattern doesn't match.
    """
    match = re.search(SUBJECT_PATTERN, subject, re.IGNORECASE)
    if not match:
        return None
    campaign_name = match.group(1).strip()
    tiktok_handle = match.group(2).strip().lstrip("@")
    return campaign_name, tiktok_handle


def _extract_drive_links(text: str) -> list[str]:
    """텍스트에서 구글 드라이브 링크 추출."""
    return re.findall(
        r"https://drive\.google\.com/[^\s<>\"']+",
        text,
    )


def _get_message_body(msg: dict) -> str:
    """메일 본문 텍스트 추출."""
    def _decode_part(part):
        data = part.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return ""

    payload = msg.get("payload", {})
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        return _decode_part(payload)

    if mime_type.startswith("multipart"):
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain":
                return _decode_part(part)
            # 중첩 multipart
            if part.get("mimeType", "").startswith("multipart"):
                for subpart in part.get("parts", []):
                    if subpart.get("mimeType") == "text/plain":
                        return _decode_part(subpart)
    return ""


def _get_attachments(service, user_id: str, msg: dict) -> list[tuple[str, bytes]]:
    """메일 첨부파일 중 영상 파일만 추출.

    Returns list of (filename, file_bytes).
    """
    results = []
    payload = msg.get("payload", {})

    def _process_parts(parts):
        for part in parts:
            filename = part.get("filename", "")
            mime_type = part.get("mimeType", "")
            ext = Path(filename).suffix.lower() if filename else ""

            # 영상 파일이거나 video/* MIME 타입
            if ext in VIDEO_EXTENSIONS or mime_type.startswith("video/"):
                att_id = part.get("body", {}).get("attachmentId")
                if att_id:
                    att = service.users().messages().attachments().get(
                        userId=user_id,
                        messageId=msg["id"],
                        id=att_id,
                    ).execute()
                    file_bytes = base64.urlsafe_b64decode(att["data"])
                    results.append((filename, file_bytes))

            # 중첩 parts 처리
            if "parts" in part:
                _process_parts(part["parts"])

    _process_parts(payload.get("parts", []))
    return results


class IncomingMail:
    """파싱된 수신 메일."""
    def __init__(
        self,
        message_id: str,
        account: str,
        campaign_name: str,
        tiktok_handle: str,
        subject: str,
        drive_links: list[str],
        attachments: list[tuple[str, bytes]],  # [(filename, bytes), ...]
    ):
        self.message_id = message_id
        self.account = account
        self.campaign_name = campaign_name
        self.tiktok_handle = tiktok_handle
        self.subject = subject
        self.drive_links = drive_links
        self.attachments = attachments

    @property
    def has_video(self) -> bool:
        return bool(self.attachments)

    @property
    def has_drive_link(self) -> bool:
        return bool(self.drive_links)

    def __repr__(self):
        return (
            f"IncomingMail(campaign={self.campaign_name!r}, "
            f"creator={self.tiktok_handle!r}, "
            f"attachments={len(self.attachments)}, "
            f"drive_links={len(self.drive_links)})"
        )


def poll_new_mails(max_results: int = 20) -> list[IncomingMail]:
    """모든 감시 계정에서 새 메일 폴링.

    제목 패턴([캠페인명] @핸들)에 맞는 미처리 메일만 반환.
    """
    processed_ids = _load_processed_ids()
    results = []

    for account in GMAIL_ACCOUNTS:
        try:
            service = _get_gmail_service(account)
            mails = _poll_account(service, account, processed_ids, max_results)
            results.extend(mails)
        except Exception as e:
            print(f"[gmail_watcher] {account} 폴링 실패: {e}")

    return results


def _poll_account(
    service,
    account: str,
    processed_ids: set[str],
    max_results: int,
) -> list[IncomingMail]:
    """단일 계정 폴링."""
    results = []

    # 최근 N개 메일 조회 (읽지 않은 메일만)
    response = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        q="is:unread",
    ).execute()

    messages = response.get("messages", [])

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        if msg_id in processed_ids:
            continue

        # 메일 전체 내용 조회
        msg = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full",
        ).execute()

        # 제목 추출
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "")

        # 제목 패턴 매칭
        parsed = _parse_subject(subject)
        if not parsed:
            # 패턴 불일치 → 스킵 (처리 완료로 기록하지 않음)
            continue

        campaign_name, tiktok_handle = parsed

        # 본문에서 드라이브 링크 추출
        body = _get_message_body(msg)
        drive_links = _extract_drive_links(body)

        # 첨부파일 영상 추출
        attachments = _get_attachments(service, "me", msg)

        if not drive_links and not attachments:
            # 영상도 링크도 없으면 스킵
            print(f"[gmail_watcher] {subject!r} — 영상/링크 없음, 스킵")
            continue

        mail = IncomingMail(
            message_id=msg_id,
            account=account,
            campaign_name=campaign_name,
            tiktok_handle=tiktok_handle,
            subject=subject,
            drive_links=drive_links,
            attachments=attachments,
        )
        results.append(mail)
        print(f"[gmail_watcher] 신규 메일 감지: {mail}")

    return results


def mark_processed(message_id: str) -> None:
    """메일 처리 완료 표시."""
    _save_processed_id(message_id)

"""Slack 알림 모듈.

AI 검수 완료 시 지정 채널에 알림 발송.
"""
from __future__ import annotations

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from pipeline.config_pipeline import SLACK_BOT_TOKEN, SLACK_CHANNEL_ID


def _get_client() -> WebClient:
    if not SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN이 설정되지 않았습니다.")
    return WebClient(token=SLACK_BOT_TOKEN)


def notify_review_complete(
    campaign_name: str,
    tiktok_handle: str,
    score: int,
    status: str,
    sheet_url: str,
    manual_flags: list[str] | None = None,
) -> bool:
    """AI 검수 완료 알림 발송.

    Returns True if sent successfully.
    """
    client = _get_client()

    status_emoji = {
        "approved": "✅ 승인",
        "auto_approved": "✅ 자동승인",
        "revision_needed": "🔄 수정필요",
        "rejected": "❌ 반려",
    }.get(status, status)

    # 메인 메시지
    text = (
        f"*[{campaign_name}] @{tiktok_handle} — AI 1차 검수 완료*\n"
        f"점수: *{score}점* | 상태: {status_emoji}\n"
    )

    # 수동 확인 필요 항목
    if manual_flags:
        text += f"\n⚠️ *사람 확인 필요 ({len(manual_flags)}건):*\n"
        for flag in manual_flags[:3]:  # 최대 3개만 표시
            text += f"• {flag}\n"
        if len(manual_flags) > 3:
            text += f"• ... 외 {len(manual_flags) - 3}건\n"

    text += f"\n📊 <{sheet_url}|캠페인 보드에서 확인>"

    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            text=text,
            mrkdwn=True,
        )
        print(f"[slack_notifier] 알림 발송 완료: @{tiktok_handle} ({score}점)")
        return True
    except SlackApiError as e:
        print(f"[slack_notifier] 발송 실패: {e.response['error']}")
        return False


def notify_error(
    campaign_name: str,
    tiktok_handle: str,
    error_msg: str,
) -> None:
    """파이프라인 오류 알림."""
    client = _get_client()
    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            text=(
                f"🚨 *파이프라인 오류*\n"
                f"캠페인: {campaign_name} | 크리에이터: @{tiktok_handle}\n"
                f"오류: {error_msg}"
            ),
            mrkdwn=True,
        )
    except SlackApiError:
        pass  # 알림 오류는 무시

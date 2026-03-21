"""Pipeline 설정값.

나중에 캠페인 DB 완성되면 이 파일의 CAMPAIGN_CONFIGS를
DB 쿼리로 교체하면 됨.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _e(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ── Google OAuth ────────────────────────────────────────
# Google Cloud Console에서 OAuth 2.0 클라이언트 ID 생성 후 다운로드
# https://console.cloud.google.com/apis/credentials
GOOGLE_CREDENTIALS_PATH = _e("GOOGLE_CREDENTIALS_PATH", "pipeline/credentials.json")
GOOGLE_TOKEN_PATH = _e("GOOGLE_TOKEN_PATH", "pipeline/token.json")

# ── Gmail 감시 계정 ──────────────────────────────────────
GMAIL_ACCOUNTS = [
    "team_heroines@4am.team",
    "mila@4am.team",
]

# 메일 제목 파싱 규칙: [캠페인명] @틱톡핸들 ...
# 예: [Magis Lene] @lisasvoging 1차 영상
SUBJECT_PATTERN = r"\[(.+?)\]\s*@([\w.]+)"

# Gmail 폴링 간격 (초) — 5분마다 체크
POLL_INTERVAL_SECONDS = 300

# ── Google Drive ─────────────────────────────────────────
# 영상 저장할 드라이브 폴더 ID
DRIVE_FOLDER_ID = _e("DRIVE_FOLDER_ID", "1i0oF_0cf9ebcUUCCpAJBLGiCcyWwtHjs")

# ── 캠페인별 시트 매핑 ────────────────────────────────────
# 나중에 캠페인 DB 완성되면 DB 쿼리로 교체
# key: 캠페인명 (메일 제목의 [캠페인명] 부분)
# value: 시트 정보
CAMPAIGN_CONFIGS = {
    "Magis Lene": {
        "sheet_id": "1DWgBz5ayhb_KRpkWU_1M92vFmLa8anERisGU154_1yY",
        "sheet_tab": "소재 수급 리스트",
        "guideline_name": "Magis Lene",  # vc_guidelines의 campaign_name
    },
    # 새 캠페인 추가 시 여기에 추가
    # "Brand Name": {
    #     "sheet_id": "...",
    #     "sheet_tab": "소재 수급 리스트",
    #     "guideline_name": "...",
    # },
}

# 시트 컬럼 (A=1 기준)
COL_TIKTOK_ID = "C"    # TikTok ID (username)
COL_1ST_DRAFT = "M"    # 1st Draft — 드라이브 링크 기입
COL_COMMENT   = "N"    # 새벽네시 코멘트 — AI 검수 결과 기입
COL_UPDATE_DATE = "A"  # Update date

# ── Slack ────────────────────────────────────────────────
SLACK_BOT_TOKEN  = _e("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = _e("SLACK_CHANNEL_ID", "C0AE6130VHT")

# ── 처리 상태 추적 (중복 실행 방지) ──────────────────────
# 처리 완료된 Gmail message ID를 저장하는 파일
PROCESSED_IDS_PATH = _e("PROCESSED_IDS_PATH", "pipeline/.processed_ids.txt")

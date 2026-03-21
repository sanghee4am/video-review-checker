"""OAuth 최초 인증 스크립트.

각 Gmail 감시 계정에 대해 브라우저 OAuth 승인을 한 번씩 수행.
승인 후 pipeline/token_{계정}.json 파일이 자동 생성됨.

실행:
    python -m pipeline.auth_setup
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from google_auth_oauthlib.flow import InstalledAppFlow
from pipeline.config_pipeline import GOOGLE_CREDENTIALS_PATH, GMAIL_ACCOUNTS

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def auth_account(account: str) -> None:
    token_path = f"pipeline/token_{account.replace('@','_').replace('.','_')}.json"
    if os.path.exists(token_path):
        print(f"[auth_setup] ✅ 이미 인증됨: {account} → {token_path}")
        return

    print(f"\n[auth_setup] 브라우저에서 {account} 계정으로 승인해주세요...")
    flow = InstalledAppFlow.from_client_secrets_file(
        GOOGLE_CREDENTIALS_PATH,
        scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    auth_url, _ = flow.authorization_url(
        login_hint=account,
        prompt="consent",
        access_type="offline",
    )
    print(f"\n아래 URL을 브라우저에서 열고 {account} 계정으로 승인 후 코드를 복사하세요:")
    print(f"\n{auth_url}\n")
    code = input("승인 코드 붙여넣기: ").strip()
    flow.fetch_token(code=code)
    creds = flow.credentials

    import json
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    print(f"[auth_setup] ✅ 토큰 저장 완료: {token_path}")


if __name__ == "__main__":
    print(f"감시 계정 {len(GMAIL_ACCOUNTS)}개 인증 시작...")
    for account in GMAIL_ACCOUNTS:
        auth_setup = auth_account(account)
    print("\n[auth_setup] 모든 계정 인증 완료! 이제 파이프라인을 실행할 수 있어요.")
    print("실행 방법: python -m pipeline.main --loop")

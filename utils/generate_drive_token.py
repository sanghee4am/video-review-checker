"""Drive API 토큰 생성 스크립트.

1회만 실행하면 됨. 브라우저에서 Google 로그인 → 토큰 생성 → 출력.
출력된 JSON을 Streamlit Cloud secrets에 GOOGLE_DRIVE_TOKEN으로 추가.
"""
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CREDENTIALS_PATH = Path(__file__).parent.parent / "pipeline" / "credentials.json"


def main():
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = json.loads(creds.to_json())
    print("\n" + "=" * 60)
    print("아래 JSON을 Streamlit Cloud secrets에 추가하세요:")
    print('GOOGLE_DRIVE_TOKEN = \'이 내용을 복사\'')
    print("=" * 60)
    print(json.dumps(token_data))
    print("=" * 60)


if __name__ == "__main__":
    main()

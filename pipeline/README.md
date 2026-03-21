# Pipeline — 영상 검수 자동화

메일 수신 → 드라이브 저장 → 시트 기입 → AI 검수 → Slack 알림

```
Gmail (team_heroines, mila)
  └─ [캠페인명] @핸들 형식 메일 감지
       ├─ 첨부파일(영상) → Drive 업로드
       └─ 본문 드라이브 링크 → Drive 복사
            ↓
     캠페인보드 M열(1st Draft) 링크 기입
            ↓
     AI 검수 (process_video + run_compliance_check)
            ↓
     캠페인보드 N열(새벽네시 코멘트) 결과 기입
            ↓
     Slack #알림채널 알럿
```

---

## 1. Google Cloud Console 설정

1. [Google Cloud Console](https://console.cloud.google.com) → 프로젝트 선택
2. **API 및 서비스 > API 라이브러리** 에서 아래 3개 활성화:
   - Gmail API
   - Google Drive API
   - Google Sheets API
3. **사용자 인증 정보 > OAuth 2.0 클라이언트 ID** 생성
   - 애플리케이션 유형: **데스크톱 앱**
   - 생성 후 JSON 다운로드
4. 다운로드한 파일을 `pipeline/credentials.json`으로 저장

> ⚠️ `credentials.json`은 `.gitignore`에 추가 필수

---

## 2. 환경변수 설정

루트의 `.env` 파일에 추가:

```env
# Google OAuth
GOOGLE_CREDENTIALS_PATH=pipeline/credentials.json
GOOGLE_TOKEN_PATH=pipeline/token.json

# Google Drive — 영상 저장 루트 폴더 ID
# (드라이브 URL: https://drive.google.com/drive/folders/{FOLDER_ID})
DRIVE_FOLDER_ID=1i0oF_0cf9ebcUUCCpAJBLGiCcyWwtHjs

# Slack Bot Token (Slack App의 OAuth & Permissions > Bot Token)
SLACK_BOT_TOKEN=xoxb-...

# Slack 알림 채널 ID (채널 우클릭 > 링크 복사 > 마지막 부분)
SLACK_CHANNEL_ID=C0AE6130VHT

# 처리 완료 메일 ID 기록 경로 (중복 방지)
PROCESSED_IDS_PATH=pipeline/.processed_ids.txt
```

---

## 3. 최초 실행 — OAuth 인증

처음 실행 시 브라우저가 열리며 Google 계정 권한 승인 필요.
승인 완료 후 `pipeline/token_*.json` 파일이 자동 생성됨.

감시 계정(`team_heroines@4am.team`, `mila@4am.team`)마다 각각 승인 필요.

```bash
# 패키지 설치
pip install -r requirements.txt

# 1회 실행 (첫 실행 시 OAuth 브라우저 팝업)
python -m pipeline.main
```

---

## 4. 실행 방법

```bash
# 한 번만 실행 (cron 등 외부 스케줄러 사용 시)
python -m pipeline.main

# 5분 간격 루프 실행 (백그라운드 프로세스)
python -m pipeline.main --loop

# 백그라운드 실행 (nohup)
nohup python -m pipeline.main --loop > pipeline/pipeline.log 2>&1 &
```

---

## 5. 새 캠페인 추가

`pipeline/config_pipeline.py`의 `CAMPAIGN_CONFIGS`에 추가:

```python
CAMPAIGN_CONFIGS = {
    "Magis Lene": {
        "sheet_id": "1DWgBz5ayhb_...",
        "sheet_tab": "소재 수급 리스트",
        "guideline_name": "Magis Lene",   # vc_guidelines의 campaign_name
    },
    # 여기에 추가 ↓
    "New Brand": {
        "sheet_id": "스프레드시트_ID",
        "sheet_tab": "소재 수급 리스트",
        "guideline_name": "New Brand",
    },
}
```

그리고 **어드민 검수기**에서 해당 캠페인의 가이드라인을 등록해야 AI 검수가 작동함.

---

## 6. 메일 형식 안내 (크리에이터에게 공유)

메일 제목을 반드시 아래 형식으로 보내도록 안내:

```
[캠페인명] @틱톡핸들 1차 영상

예시:
[Magis Lene] @lisasvoging 1차 영상
[Magis Lene] @lisasvoging 1차 수정본
```

첨부 방식:
- **영상 직접 첨부** (.mp4, .mov, .avi, .mkv, .webm, .m4v)
- **구글 드라이브 링크** 본문에 붙여넣기

---

## 7. 나중에 캠페인 DB 완성 시 마이그레이션

현재 `config_pipeline.py`의 `CAMPAIGN_CONFIGS` dict를 DB 쿼리로 교체:

```python
# 현재 (임시)
config = CAMPAIGN_CONFIGS.get(campaign_name)

# 나중에 (캠페인 DB 완성 후)
config = db.get_campaign_config(campaign_name)
```

`pipeline/` 폴더 자체는 유지하거나, 캠페인 DB 모듈과 통합 후 삭제.

---

## 파일 구조

```
pipeline/
  __init__.py         # 패키지 초기화
  config_pipeline.py  # 설정값 (캠페인 매핑, Slack 채널 등)
  gmail_watcher.py    # Gmail 폴링 + 메일 파싱
  drive_handler.py    # Google Drive 업로드/복사/다운로드
  sheet_updater.py    # Google Sheets M/N열 기입
  slack_notifier.py   # Slack 알림
  video_reviewer.py   # AI 검수 래퍼 (기존 검수기 재활용)
  main.py             # 전체 오케스트레이터
  credentials.json    # ← gitignore (직접 추가)
  token_*.json        # ← gitignore (자동 생성)
  .processed_ids.txt  # ← gitignore (자동 생성)
  README.md           # 이 파일
```

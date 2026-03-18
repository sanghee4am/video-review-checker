# Video Review Checker - Project Rules

## Overview
크리에이터 영상 가이드라인 검수 자동화 Streamlit 앱.
- Admin(app.py): 브랜드 담당자가 가이드라인 기반으로 영상 검수
- Creator(pages/1_Creator_Upload.py): 크리에이터가 직접 영상 업로드 & 결과 확인

## Deployment
- **Streamlit Cloud** — GitHub push 시 자동 배포
- 새 패키지 추가 시 `requirements.txt` 업데이트 후 Streamlit Cloud에서 Reboot 필요
- 시스템 패키지는 `packages.txt`에 추가
- Secrets: `st.secrets` (Streamlit Cloud) + `os.getenv` (로컬) → `config.py`의 `_get_secret()` 사용

## Supabase Rules (중요!)
- **기존 테이블은 절대 쓰기 금지** — SELECT(읽기)만 허용
- 새로 만드는 테이블은 반드시 `vc_` prefix 사용 (예: `vc_reviews`, `vc_submissions`)
- DB 함수는 모두 `db.py`에 작성
- **신규 테이블 생성 전 반드시 회고:**
  1. 기존 테이블에 컬럼 추가로 해결 가능한가? (1:1 관계면 컬럼이 낫다)
  2. 정말 별도 엔티티인가? (독립적 생명주기를 가지는 데이터만 테이블로)
  3. 테이블 수가 늘어날수록 조인/관리 비용 증가 — 최소한의 테이블 유지

## Project Structure
```
app.py                  # Admin 메인 페이지
pages/
  1_Creator_Upload.py   # 크리에이터 업로드 페이지 (한/영 지원)
config.py               # 설정 & secrets
db.py                   # Supabase DB 함수
models/
  review_result.py      # Pydantic 모델 (ReviewReport, SceneReview 등)
processors/
  video_processor.py    # 영상 처리 (process_video, process_videos_parallel)
utils/
  gdrive_video.py       # Google Drive 영상 다운로드 (gdown)
analyzer/               # 영상 분석 로직
```

## Key Patterns
- `process_video(video_bytes: bytes, filename: str)` — 인자 순서 주의!
- Admin UI 언어: 한국어
- Creator UI 언어: 한국어/영어 전환 가능 (`TEXTS` dict + `t()` helper)
- i18n은 각 페이지 내 `TEXTS` dict 방식 사용

## Git Workflow
- commit 후 push하면 Streamlit Cloud 자동 배포
- 브랜치: main 직접 push

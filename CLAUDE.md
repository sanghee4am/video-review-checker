# Video Review Checker - Project Rules

## Overview
크리에이터 영상 가이드라인 검수 자동화 시스템.
- **Streamlit은 선셋** (2026-03-30) — 모든 UI가 Workers + Docker :3001로 이관됨
- 이 폴더의 Python 코드는 **FastAPI :3003 백엔드** + **pipeline CLI**로 동작
- 프론트엔드: Workers `/g/` (크리에이터), `/b/` (브랜드), Docker `:3001` (어드민)

## 시스템 구조 (2026-03-30~)
```
[크리에이터]  Workers /g/:glId/:username
[브랜드]     Workers /b/:glId
[어드민]     Docker :3001 /dashboard/*  (Next.js)
[영상처리]   FastAPI :3003              (이 폴더의 api_main.py)
[파이프라인]  python -m pipeline.main   (이 폴더의 pipeline/)
[DB]        Supabase (8 tables, 9 FKs)
```

## 전체 파이프라인
1. **가이드라인 파싱** — PDF/엑셀/이미지/CSV/URL(GDrive, Sheets, Slides) → AI 파싱 → 구조화 → `guidelines.gl_parsed_json` 저장
2. **영상 전처리** — ffmpeg 프레임 추출 + Whisper STT, 병렬 처리, GDrive 다운로드
3. **AI 검수** — 2단계(배치 프레임 분석 → 종합 검수), 장면별 pass/fail/warning, 재검수 시 이전 리뷰 비교
4. **자동 산출물** — 수정 안내 이메일 한/영, 브랜드사 전달용 코멘트, 캡컷 편집 팁
5. **90+ 자동승인** — 90점 이상 & 수동 플래그 없음 → 자동 승인
6. **어드민 수동 결정** — Docker :3001 VideoReviewSection에서 승인/수정요청/반려
7. **크리에이터 셀프서비스** — Workers /g/ 전용 링크, 드래프트 업로드, 검수 결과 확인
8. **캡션 검수** — SNS 해시태그/멘션/광고표시 AI 대조
9. **콘텐츠 검수** — 무가 캠페인 콘텐츠 URL AI 검수 (vc_content_checks 큐)
10. **브랜드 피드백 재검수 자동 연동** — 피드백→상태변경→AI프롬프트 주입→반영 여부 자동 체크

## Deployment
- **FastAPI :3003** — Mac mini에서 Docker 또는 직접 실행
  - `uvicorn api_main:app --host 0.0.0.0 --port 3003`
- **Pipeline** — 수동 1회 실행 또는 cron
  - `python3.11 -m pipeline.main`
- ~~Streamlit Cloud~~ — 2026-03-30 선셋

## Supabase Rules (중요!)
- **기존 테이블(선아님 생성)은 절대 쓰기 금지** — SELECT(읽기)만 허용 (단, `guidelines.gl_parsed_json` 업데이트는 허용)
- vc_* 테이블: `vc_reviews`, `vc_content_checks` 사용 중 (`vc_guidelines`는 삭제됨 → `guidelines.gl_parsed_json`으로 통합)
- DB 함수는 모두 `db.py`에 작성
- 가이드라인은 `guidelines` 테이블의 `gl_parsed_json` 컬럼에 저장 (gl_id = UUID)
- **모든 조회는 gl_id FK 기반** — campaign_name 텍스트 매칭 사용 금지
- **신규 테이블 생성 전 반드시 회고:**
  1. 기존 테이블에 컬럼 추가로 해결 가능한가? (1:1 관계면 컬럼이 낫다)
  2. 정말 별도 엔티티인가? (독립적 생명주기를 가지는 데이터만 테이블로)
  3. 테이블 수가 늘어날수록 조인/관리 비용 증가 — 최소한의 테이블 유지

## Project Structure
```
api_main.py             # FastAPI 백엔드 (:3003) — 영상 검수, 가이드라인 파싱, 콘텐츠 체크
db.py                   # Supabase DB 함수 (gl_id 기반)
config.py               # 설정 & secrets
models/
  guideline.py          # 가이드라인 파싱 모델 (ParsedGuideline, GuidelineRule, GuidelineScene)
  review_result.py      # 리뷰 결과 모델 (ReviewReport, SceneReview 등)
processors/
  video_processor.py    # 영상 처리 (process_video, process_videos_parallel)
  guideline_parser.py   # 가이드라인 AI 파싱
analyzer/
  compliance_checker.py # AI 검수 로직 (brand_feedback 자동 주입 포함)
  content_checker.py    # 콘텐츠 검수 (무가)
  unpaid_checker.py     # 무가 검수 로직
utils/
  gdrive_video.py       # Google Drive 영상 다운로드 (gdown)
pipeline/               # 자동화 파이프라인 (로컬 실행)
  config_pipeline.py    # 파이프라인 설정 (캠페인별 gl_id/시트/드라이브 매핑)
  drive_poller.py       # Drive 폴더 스캔 — 새 파일 감지 및 핸들 파싱
  drive_handler.py      # Drive 파일 업로드/다운로드
  sheet_updater.py      # Sheets M열(드라이브링크), N열(AI검수결과) 기입
  slack_notifier.py     # Slack 검수완료 알림
  video_reviewer.py     # AI 검수 래퍼 (process_video + run_compliance_check)
  content_check_worker.py # 콘텐츠 체크 워커
  main.py               # 파이프라인 오케스트레이터 (1회 실행)
  .processed_ids.txt    # 처리 완료된 파일 ID 기록 (중복 방지)
requirements.txt        # Python 패키지 (Streamlit 포함 — 레거시)
requirements-api.txt    # FastAPI 전용 패키지
packages.txt            # 시스템 패키지 (ffmpeg 등)

# 레거시 (선셋, 삭제 예정)
app.py                  # Streamlit Admin
pages/
  1_Creator_Upload.py   # Streamlit 크리에이터
  2_Brand_Dashboard.py  # Streamlit 브랜드
```

## Key Patterns
- `process_video(video_bytes: bytes, filename: str)` — 인자 순서 주의!
- **gl_id (UUID)로 가이드라인 참조** — `load_guideline(gl_id)` 사용
- ~~load_guideline_by_name()~~ 삭제됨
- DB 데이터 접근 시 `.get()` 사용 — 오래된 레코드에 키가 없을 수 있음
- 브랜드 피드백 재검수: `db.get_latest_brand_feedback()` → `compliance_checker.py`에 자동 주입

## Pipeline 사용법
크리에이터 영상을 수동으로 드라이브 폴더에 업로드한 뒤 아래 커맨드 1회 실행.

**파일명 규칙:** `{틱톡핸들}_{파일명}.mp4`
예: `lucyhan_draft1.mp4`, `nipzreal07_video.mov`

**드라이브 폴더:**
- 1차 드래프트: `https://drive.google.com/drive/folders/1i0oF_0cf9ebcUUCCpAJBLGiCcyWwtHjs`
- 2차 드래프트: `https://drive.google.com/drive/folders/1b76QTr66XCDSgryev-RUdQytt93lx5gJ`

**실행:**
```bash
cd ~/히로인즈/workflows/video-review-checker
python3.11 -m pipeline.main
```

실행하면 새 파일 자동 감지 → AI 검수 → 시트 M/N열 기입 → Slack 알림까지 한 번에 처리.
이미 처리된 파일은 `pipeline/.processed_ids.txt`에 기록되어 재처리되지 않음.

**새 캠페인 추가 시:** `pipeline/config_pipeline.py`의 `CAMPAIGN_CONFIGS`에 gl_id 포함하여 추가.

## 최근 변경 이력
- (2026-03-30): **시스템 통합 완료** — Streamlit 선셋, Workers + Docker :3001 + FastAPI :3003 체제
  - 모든 코드 gl_id FK 기반으로 변경 (campaign_name 텍스트 매칭 제거)
  - vc_guidelines 테이블 DROP → guidelines.gl_parsed_json 통합
  - vc_reviews.campaign_id (bigint FK) → vc_reviews.gl_id (uuid FK)
  - Workers /g/, /b/ 경로에 gl_id 필터 추가 (크로스캠페인 버그 수정)
  - pipeline/config_pipeline.py: guideline_name → gl_id
  - 통합 현황 문서: workflows/migration-plan.html
- `fdaee69` (2026-03-29): db.py streamlit 의존성 제거 (lru_cache로 대체)
- `365959a` (2026-03-29): FastAPI 포트 3002→3003 변경 (3002는 대시보드 테스트용)
- `6ad4316` (2026-03-29): FastAPI 백엔드 추가 (Streamlit → API 마이그레이션)
- `d672778` (2026-03-27): API 529 Overloaded 에러 재시도 추가
- `ab8bfce` (2026-03-27): 메모리 최적화 — Supabase 클라이언트 캐싱, DB 쿼리 .limit(), 프레임 메모리 정리
- `2026-03-21`: 메일 기반 파이프라인 → 드라이브 폴더 폴링 방식으로 전환

# Video Review Checker - Project Rules

## Overview
크리에이터 영상 가이드라인 검수 자동화 Streamlit 앱. PHASE 1-5 전체 파이프라인 완성 (2026-03-19).
- Admin(app.py): 브랜드 담당자가 가이드라인 기반으로 영상 검수, 캠페인 관리, 브랜드 피드백 전달
- Creator(pages/1_Creator_Upload.py): 크리에이터가 직접 영상 업로드 & 결과 확인 (한/영 지원)

## 전체 파이프라인
1. **가이드라인 파싱** — PDF/엑셀/이미지/CSV/URL(GDrive, Sheets, Slides) → AI 파싱 → 구조화 → DB 저장
2. **영상 전처리** — ffmpeg 프레임 추출 + Whisper STT, 병렬 처리, GDrive 다운로드
3. **AI 검수** — 2단계(배치 프레임 분석 → 종합 검수), 장면별 pass/fail/warning, 재검수 시 이전 리뷰 비교
4. **자동 산출물** — 수정 안내 이메일 한/영, 브랜드사 전달용 코멘트, 캡컷 편집 팁
5. **90+ 자동승인** — 90점 이상 & 수동 플래그 없음 → 자동 승인
6. **어드민 대시보드** — 캠페인 현황, 크리에이터별 상세 이력, 수동 결정, 브랜드 피드백
7. **크리에이터 셀프서비스** — 전용 링크, 한/영 전환, 5단계 스텝, 편집 팁, 수정 체크리스트
8. **캡션 검수** — SNS 해시태그/멘션/광고표시 AI 대조
9. **브랜드 피드백 재검수 자동 연동** — 피드백→상태변경→AI프롬프트 주입→반영 여부 자동 체크

## Deployment
- **Streamlit Cloud** — GitHub push 시 자동 배포
- URL: `https://video-review-checker-2f6utmtejjnlbpi3xy5tsq.streamlit.app/`
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
app.py                  # Admin 메인 페이지 (~1800줄, 5개 탭)
pages/
  1_Creator_Upload.py   # 크리에이터 업로드 페이지 (한/영 지원)
config.py               # 설정 & secrets
db.py                   # Supabase DB 함수
models/
  guideline.py          # 가이드라인 파싱 모델 (ParsedGuideline, GuidelineRule, GuidelineScene)
  review_result.py      # 리뷰 결과 모델 (ReviewReport, SceneReview 등)
processors/
  video_processor.py    # 영상 처리 (process_video, process_videos_parallel)
analyzer/
  compliance_checker.py # AI 검수 로직 (brand_feedback 자동 주입 포함)
utils/
  gdrive_video.py       # Google Drive 영상 다운로드 (gdown)
pipeline/               # 자동화 파이프라인 (로컬 실행)
  config_pipeline.py    # 파이프라인 설정 (캠페인별 시트/드라이브/가이드라인 매핑)
  drive_poller.py       # Drive 폴더 스캔 — 새 파일 감지 및 핸들 파싱
  drive_handler.py      # Drive 파일 업로드/다운로드
  sheet_updater.py      # Sheets M열(드라이브링크), N열(AI검수결과) 기입
  slack_notifier.py     # Slack 검수완료 알림
  video_reviewer.py     # AI 검수 래퍼 (process_video + run_compliance_check)
  main.py               # 파이프라인 오케스트레이터 (1회 실행)
  .processed_ids.txt    # 처리 완료된 파일 ID 기록 (중복 방지)
requirements.txt        # Python 패키지
packages.txt            # 시스템 패키지 (ffmpeg 등)
```

## Key Patterns
- `process_video(video_bytes: bytes, filename: str)` — 인자 순서 주의!
- Admin UI 언어: 한국어
- Creator UI 언어: 한국어/영어 전환 가능 (`TEXTS` dict + `t()` helper)
- i18n은 각 페이지 내 `TEXTS` dict 방식 사용
- DB 데이터 접근 시 `.get()` 사용 — 오래된 레코드에 키가 없을 수 있음
- 브랜드 피드백 재검수: `db.get_latest_brand_feedback()` → `compliance_checker.py`에 자동 주입

## Git Workflow
- commit 후 push하면 Streamlit Cloud 자동 배포
- 브랜치: main 직접 push

## Pipeline 사용법
크리에이터 영상을 수동으로 드라이브 폴더에 업로드한 뒤 아래 커맨드 1회 실행.

**파일명 규칙:** `{틱톡핸들}_{파일명}.mp4`
예: `lucyhan_draft1.mp4`, `nipzreal07_video.mov`

**드라이브 폴더:**
- 1차 드래프트: `https://drive.google.com/drive/folders/1i0oF_0cf9ebcUUCCpAJBLGiCcyWwtHjs`
- 2차 드래프트: `https://drive.google.com/drive/folders/1b76QTr66XCDSgryev-RUdQytt93lx5gJ`

**실행:**
```bash
cd ~/video-review-checker
python3.11 -m pipeline.main
```

실행하면 새 파일 자동 감지 → AI 검수 → 시트 M/N열 기입 → Slack 알림까지 한 번에 처리.
이미 처리된 파일은 `pipeline/.processed_ids.txt`에 기록되어 재처리되지 않음.

**새 캠페인 추가 시:** `pipeline/config_pipeline.py`의 `CAMPAIGN_CONFIGS`에 추가.

## 최근 변경 이력
- `fdaee69` (2026-03-29): db.py streamlit 의존성 제거 (lru_cache로 대체)
- `365959a` (2026-03-29): FastAPI 포트 3002→3003 변경 (3002는 대시보드 테스트용)
- `6ad4316` (2026-03-29): FastAPI 백엔드 추가 (Streamlit → API 마이그레이션)
- `d672778` (2026-03-27): API 529 Overloaded 에러 재시도 추가 — OverloadedError도 RateLimitError와 동일하게 최대 5회 재시도
- `ab8bfce` (2026-03-27): 메모리 최적화 — Supabase 클라이언트 @st.cache_resource 캐싱, DB 쿼리 .limit() 추가, 검수 후 프레임 메모리 정리
- `27f99a0`: 영상 Drive 링크 저장 + 브랜드 대시보드에 영상 보기 링크 표시
- `5261327`: 브랜드 대시보드에 Draft 필터 추가 (전체/1차/2차)
- `2026-03-21`: 메일 기반 파이프라인 → 드라이브 폴더 폴링 방식으로 전환
  - `drive_poller.py` 신규 — 1st/2nd Draft 폴더 스캔, 파일명에서 틱톡핸들 파싱
  - `main.py` 교체 — 드라이브 파일 기반 1회 실행 방식
  - `config_pipeline.py` — `drive_folder_1st`, `drive_folder_2nd` 추가
  - `gmail_watcher.py` 비활성화 (파일은 유지, main에서 미사용)
- `be6311b` (2026-03-20): creator_name 키 없는 레코드 크래시 방지 (.get() 처리)
- `e93ba8a` (2026-03-20): 워크플로우 끊김 수정 — 어드민 결정 항상 표시, 크리에이터 필수화, 씬 상세 복원, 링크 관리
- `3ae2124`: 검수 로딩바 최상단 이동 + Tab1 상세에 전체 검수 결과 뷰
- `c80ca2e`: 어드민 워크플로우 연결고리 개선
- `b18210b`: 브랜드 피드백 재검수 자동 연동
- `1ec5585`: Tab 1 관리 중심 재구성 + Tab 4 중복 제거
- `12f6fc0`: 어드민/크리에이터 역할 분리 UI
- `f906859`: PHASE 4-5 완성 및 크리에이터 UX 개선

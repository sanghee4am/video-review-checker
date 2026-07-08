"""HEVC(H.265) → H.264 mp4 자동 트랜스코딩.

크리에이터가 iPhone 기본 카메라로 촬영한 HEVC 영상은 Chrome/Edge/Firefox
등 대부분의 브라우저에서 재생이 안 되어 검수 페널·브랜드 페이지에서
검은 화면만 뜬다. app-guideline이 draft 업로드 완료 후 이 API를 호출하면
백그라운드로 ffprobe로 코덱 감지 → HEVC이면 ffmpeg로 H.264 mp4 변환 →
Supabase Storage에 신규 파일 업로드 → DB의 ci_{N}th_draft_urls 배열에서
원본 경로를 새 경로로 교체한다. 원본은 백업 삼아 그대로 둔다.

H.264 아닌 다른 웹 미지원 코덱(ProRes 등)도 함께 커버하려면
_should_transcode()의 판정 로직을 확장하면 된다.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import os
from functools import lru_cache
from supabase import create_client, Client

from config import SUPABASE_URL


@lru_cache(maxsize=1)
def _get_client() -> Client:
    """Storage 업로드 + campaign_influencers UPDATE 용.

    Service role key가 있으면 RLS 우회, 없으면 기본 SUPABASE_KEY(anon)로 폴백.
    맥미니 컨테이너 재시작 시 SUPABASE_SERVICE_ROLE_KEY 환경변수를 넘겨주면 안전.
    """
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not SUPABASE_URL or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_(SERVICE_ROLE_)KEY required")
    return create_client(SUPABASE_URL, key)

COLUMN_BY_ROUND: dict[int, str] = {
    1: "ci_1st_draft_urls",
    2: "ci_2nd_draft_urls",
    3: "ci_3rd_draft_urls",
    4: "ci_4th_draft_urls",
}

# 웹에서 정상 재생되는 코덱. 그 외(hevc/h265/prores/...)는 변환 대상.
WEB_SAFE_CODECS: set[str] = {"h264", "avc1", "vp8", "vp9", "av1"}


def _probe_codec(path: str) -> str | None:
    """첫 번째 비디오 스트림의 코덱 이름을 소문자로 반환. 실패 시 None."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        codec = result.stdout.strip().lower()
        return codec or None
    except Exception as e:
        print(f"[transcoder] ffprobe failed for {path}: {e}")
        return None


def _should_transcode(codec: str | None) -> bool:
    """웹 재생 불가 코덱이면 True. 감지 실패(None)면 안전상 False(변환 안 함)."""
    if codec is None:
        return False
    return codec not in WEB_SAFE_CODECS


def _transcode_to_h264(src: str, dst: str) -> None:
    """src(임의 코덱) → dst(H.264 mp4). CRF 23 · 웹 재생 최적화 flag 포함."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", src,
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "medium",
            "-pix_fmt", "yuv420p",       # 10bit HDR → 8bit SDR (브라우저 호환)
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",   # moov atom 앞으로 → progressive 재생
            dst,
        ],
        check=True,
        capture_output=True,
        timeout=1800,  # 30분
    )


def process_draft_file(ci_id: str, path: str, bucket: str, column: str) -> dict[str, Any]:
    """단일 파일 처리. 결과 dict 반환."""
    sb = _get_client()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = os.path.basename(path)
            stem = Path(filename).stem

            src = os.path.join(tmpdir, filename)

            # Supabase Storage 다운로드
            data = sb.storage.from_(bucket).download(path)
            with open(src, "wb") as f:
                f.write(data)

            # 코덱 감지
            codec = _probe_codec(src)
            print(f"[transcoder] {path} codec={codec}")
            if not _should_transcode(codec):
                return {"path": path, "codec": codec, "action": "skip"}

            # 변환
            dst_name = f"{stem}_h264.mp4"
            dst = os.path.join(tmpdir, dst_name)
            _transcode_to_h264(src, dst)

            # 새 경로 (원본과 같은 폴더)
            folder = os.path.dirname(path)
            new_path = f"{folder}/{dst_name}" if folder else dst_name

            # 업로드 (기존에 같은 이름 있으면 덮어씀)
            with open(dst, "rb") as f:
                sb.storage.from_(bucket).upload(
                    new_path,
                    f.read(),
                    file_options={"content-type": "video/mp4", "upsert": "true"},
                )

            # DB UPDATE: 배열에서 원본 경로 → 새 경로로 in-place 교체
            row = sb.table("campaign_influencers").select(column).eq("id", ci_id).single().execute()
            urls = row.data.get(column) or []
            new_urls = [new_path if u == path else u for u in urls]
            sb.table("campaign_influencers").update({column: new_urls}).eq("id", ci_id).execute()

            print(f"[transcoder] {path} -> {new_path} (transcoded from {codec})")
            return {
                "path": path,
                "codec": codec,
                "action": "transcoded",
                "new_path": new_path,
            }

    except subprocess.CalledProcessError as e:
        err = (e.stderr.decode(errors="replace")[:500] if e.stderr else str(e))
        print(f"[transcoder] ffmpeg failed for {path}: {err}")
        return {"path": path, "action": "error", "error": f"ffmpeg: {err}"}
    except Exception as e:
        print(f"[transcoder] error for {path}: {e}")
        return {"path": path, "action": "error", "error": str(e)}


def process_draft_batch(
    ci_id: str,
    paths: list[str],
    draft_round: int,
    bucket: str = "drafts",
) -> list[dict[str, Any]]:
    """여러 파일을 순차 처리. draft_round는 1|2|3|4."""
    if draft_round not in COLUMN_BY_ROUND:
        raise ValueError(f"invalid draft_round: {draft_round}")
    column = COLUMN_BY_ROUND[draft_round]
    results = []
    for p in paths:
        results.append(process_draft_file(ci_id, p, bucket, column))
    return results

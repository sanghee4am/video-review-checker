"""Unpaid content checker — lightweight video analysis.

Downloads TikTok/IG video via yt-dlp, extracts frames at 3-second intervals,
then runs a single AI call to check:
1. Is this a multi-product showcase (not dedicated to our product)?
2. Is this a simple unboxing (no review/usage/storytelling)?

Much lighter than the full compliance_checker used for paid campaigns.
"""
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from processors.video_processor import (
    ProcessedVideo, VideoFrame,
    get_video_duration, extract_frames, resize_frame,
)

# Frame extraction: every 3 seconds (much lighter than paid 0.8s)
UNPAID_FRAME_INTERVAL = 3.0
MAX_FRAMES = 15  # cap frames to control cost


UNPAID_ANALYSIS_PROMPT = """You are reviewing a social media video for an UNPAID campaign.
The brand sent free product to a creator (no payment). We need to verify the content quality.

=== CAMPAIGN INFO ===
Brand/Product: {product_name}
Concept: {concept}

=== VIDEO CAPTION ===
{caption}

=== VIDEO FRAMES ===
{num_frames} frames extracted at {interval}s intervals from a {duration}s video are attached.

Evaluate TWO things by looking at ALL the frames:

1. **Multi-Product Check**
   - Does the video feature ONLY the brand's product, or does it showcase multiple different products/brands?
   - FAIL if: the video is a "haul", "favorites", or "collection" video showing many different brands/products where the sponsored product is just one of many.
   - PASS if: the video focuses on the brand's product (it's OK if other items appear incidentally in the background).

2. **Simple Unboxing Check**
   - Is this just a basic unboxing video (opening a package, showing what's inside, nothing more)?
   - FAIL if: the creator ONLY opens packaging and shows the product without any real usage, review, demonstration, opinion, or storytelling.
   - PASS if: the creator actually uses the product, gives opinions, shows results, demonstrates application, or tells a story.

Return ONLY valid JSON (no markdown fences):
{{
  "is_multi_product": true/false,
  "multi_product_detail": "brief explanation in English",
  "is_simple_unboxing": true/false,
  "unboxing_detail": "brief explanation in English"
}}
"""


def download_video_from_url(url: str) -> tuple[bytes, str]:
    """Download video from TikTok/IG URL using yt-dlp. Returns (video_bytes, filename)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = str(Path(tmpdir) / "video.%(ext)s")
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-playlist",
                "--max-filesize", "100M",
                "-o", output_path,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp failed: {result.stderr[:500]}")

        # Find the downloaded file
        files = list(Path(tmpdir).glob("video.*"))
        if not files:
            raise RuntimeError("yt-dlp produced no output file")

        video_path = files[0]
        video_bytes = video_path.read_bytes()
        return video_bytes, video_path.name


def process_video_light(video_bytes: bytes, filename: str) -> ProcessedVideo:
    """Light video processing — 3s intervals, no STT.

    Reuses existing frame extraction but with wider intervals.
    Skips Whisper STT to keep it fast and cheap.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = str(Path(tmpdir) / filename)
        Path(video_path).write_bytes(video_bytes)

        duration = get_video_duration(video_path)
        interval = UNPAID_FRAME_INTERVAL

        frames_dir = str(Path(tmpdir) / "frames")
        Path(frames_dir).mkdir()
        extract_frames(video_path, interval, frames_dir, duration)

        # Load and resize frames
        frame_files = sorted(Path(frames_dir).glob("frame_*.jpg"))
        frames: list[VideoFrame] = []
        for i, fp in enumerate(frame_files):
            if i >= MAX_FRAMES:
                break
            img_bytes = resize_frame(str(fp))
            timestamp = i * interval
            frames.append(VideoFrame(
                timestamp=timestamp,
                image_bytes=img_bytes,
                transcript_text="",
            ))

    return ProcessedVideo(
        duration=duration,
        frame_interval=interval,
        frames=frames,
        full_transcript="",
        transcript_segments=[],
    )


def run_unpaid_check(
    video: ProcessedVideo,
    product_name: str,
    concept: str,
    caption: str = "",
) -> dict:
    """Run the lightweight unpaid content check.

    Returns:
        {
            "is_multi_product": bool,
            "multi_product_detail": str,
            "is_simple_unboxing": bool,
            "unboxing_detail": str,
        }
    """
    # Build prompt
    prompt_text = UNPAID_ANALYSIS_PROMPT.format(
        product_name=product_name or "(unknown)",
        concept=concept or "(not specified)",
        caption=caption[:2000] if caption else "(no caption)",
        num_frames=len(video.frames),
        interval=video.frame_interval,
        duration=round(video.duration, 1),
    )

    # Build message content with frames
    content: list[dict] = [{"type": "text", "text": prompt_text}]
    for frame in video.frames:
        b64 = base64.b64encode(frame.image_bytes).decode()
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Retry logic (same as compliance_checker)
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                temperature=0,
                messages=[{"role": "user", "content": content}],
            )
            break
        except (anthropic.RateLimitError, anthropic.APIStatusError) as e:
            if attempt < max_retries - 1:
                import time
                time.sleep(5 * (attempt + 1))
            else:
                raise

    text = response.content[0].text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import openai
from PIL import Image

from config import (
    OPENAI_API_KEY,
    FRAME_INTERVAL_SHORT,
    FRAME_INTERVAL_LONG,
    SHORT_VIDEO_THRESHOLD,
    MAX_IMAGE_WIDTH,
    MAX_IMAGE_HEIGHT,
)


def _find_bin(name: str) -> str:
    """Find binary path, checking Homebrew first."""
    for candidate in [f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"]:
        if Path(candidate).exists():
            return candidate
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"{name} not found. Install via: brew install ffmpeg")


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class VideoFrame:
    timestamp: float  # seconds
    image_bytes: bytes
    transcript_text: str  # STT text for this time range


@dataclass
class ProcessedVideo:
    duration: float
    frame_interval: float
    frames: list[VideoFrame]
    full_transcript: str
    transcript_segments: list[TranscriptSegment]


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            _find_bin("ffprobe"), "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ],
        capture_output=True, text=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def extract_frames(video_path: str, interval: float, output_dir: str,
                    duration: float = 0, hook_seconds: float = 5.0,
                    hook_interval: float = 0) -> list[tuple[float, str]]:
    """Extract frames from video with adaptive intervals.

    For long videos (>= SHORT_VIDEO_THRESHOLD):
      - First `hook_seconds` at `hook_interval` (dense, for hook analysis)
      - Remainder at `interval` (normal)

    Returns list of (timestamp, frame_path) tuples.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if hook_interval > 0 and duration > 0 and hook_seconds > 0:
        # Two-pass extraction: dense hook + normal body
        hook_dir = f"{output_dir}/hook"
        body_dir = f"{output_dir}/body"
        Path(hook_dir).mkdir(parents=True, exist_ok=True)
        Path(body_dir).mkdir(parents=True, exist_ok=True)

        # Pass 1: Hook (first N seconds at dense interval)
        subprocess.run(
            [
                _find_bin("ffmpeg"), "-i", video_path,
                "-t", str(hook_seconds),
                "-vf", f"fps=1/{hook_interval}",
                "-q:v", "2", "-y",
                f"{hook_dir}/frame_%04d.jpg",
            ],
            capture_output=True, text=True,
        )

        # Pass 2: Body (after hook_seconds at normal interval)
        subprocess.run(
            [
                _find_bin("ffmpeg"), "-i", video_path,
                "-ss", str(hook_seconds),
                "-vf", f"fps=1/{interval}",
                "-q:v", "2", "-y",
                f"{body_dir}/frame_%04d.jpg",
            ],
            capture_output=True, text=True,
        )

        frames = []
        for i, fp in enumerate(sorted(Path(hook_dir).glob("frame_*.jpg"))):
            timestamp = i * hook_interval
            frames.append((timestamp, str(fp)))

        for i, fp in enumerate(sorted(Path(body_dir).glob("frame_*.jpg"))):
            timestamp = hook_seconds + i * interval
            frames.append((timestamp, str(fp)))

        return frames
    else:
        # Single-pass extraction
        subprocess.run(
            [
                _find_bin("ffmpeg"), "-i", video_path,
                "-vf", f"fps=1/{interval}",
                "-q:v", "2", "-y",
                f"{output_dir}/frame_%04d.jpg",
            ],
            capture_output=True, text=True,
        )

        frame_files = sorted(Path(output_dir).glob("frame_*.jpg"))
        frames = []
        for i, fp in enumerate(frame_files):
            timestamp = i * interval
            frames.append((timestamp, str(fp)))

        return frames


def resize_frame(frame_path: str) -> bytes:
    """Resize frame image and return as JPEG bytes."""
    img = Image.open(frame_path)
    img.thumbnail((MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def extract_audio(video_path: str, audio_path: str) -> str:
    """Extract audio track from video as mp3."""
    subprocess.run(
        [
            _find_bin("ffmpeg"), "-i", video_path,
            "-vn", "-acodec", "libmp3lame",
            "-q:a", "4",
            "-y",
            audio_path,
        ],
        capture_output=True, text=True,
    )
    return audio_path


def transcribe_audio(audio_path: str) -> tuple[str, list[TranscriptSegment]]:
    """Transcribe audio using OpenAI Whisper API.

    Returns (full_text, segments_with_timestamps).
    """
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments = []
    for seg in response.segments:
        segments.append(TranscriptSegment(
            start=seg.start if hasattr(seg, "start") else seg["start"],
            end=seg.end if hasattr(seg, "end") else seg["end"],
            text=(seg.text if hasattr(seg, "text") else seg["text"]).strip(),
        ))

    full_text = response.text
    return full_text, segments


def get_transcript_for_time(
    segments: list[TranscriptSegment],
    timestamp: float,
    interval: float,
) -> str:
    """Get transcript text that overlaps with a frame's time window."""
    window_start = timestamp
    window_end = timestamp + interval
    texts = []
    for seg in segments:
        if seg.end > window_start and seg.start < window_end:
            texts.append(seg.text)
    return " ".join(texts)


def process_video(video_bytes: bytes, filename: str) -> ProcessedVideo:
    """Full video processing pipeline: frame extraction + STT.

    Args:
        video_bytes: Raw video file bytes
        filename: Original filename (for extension detection)

    Returns:
        ProcessedVideo with frames, transcript, and timeline mapping.
    """
    ext = Path(filename).suffix or ".mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = f"{tmpdir}/input{ext}"
        frames_dir = f"{tmpdir}/frames"
        audio_path = f"{tmpdir}/audio.mp3"

        # Save video to temp file
        with open(video_path, "wb") as f:
            f.write(video_bytes)

        # Get duration and determine frame interval
        duration = get_video_duration(video_path)
        is_long = duration >= SHORT_VIDEO_THRESHOLD
        interval = FRAME_INTERVAL_SHORT if not is_long else FRAME_INTERVAL_LONG

        # Extract frames (long videos: dense 0.8s for first 5s, then normal interval)
        raw_frames = extract_frames(
            video_path, interval, frames_dir,
            duration=duration,
            hook_seconds=5.0 if is_long else 0,
            hook_interval=FRAME_INTERVAL_SHORT if is_long else 0,
        )

        # Extract and transcribe audio
        extract_audio(video_path, audio_path)
        full_transcript, segments = transcribe_audio(audio_path)

        # Build VideoFrame objects with timeline mapping
        hook_sec = 5.0 if is_long else 0
        frames = []
        for timestamp, frame_path in raw_frames:
            image_bytes = resize_frame(frame_path)
            # Use dense interval for hook, normal for body
            frame_interval = FRAME_INTERVAL_SHORT if timestamp < hook_sec else interval
            transcript_text = get_transcript_for_time(segments, timestamp, frame_interval)
            frames.append(VideoFrame(
                timestamp=timestamp,
                image_bytes=image_bytes,
                transcript_text=transcript_text,
            ))

    return ProcessedVideo(
        duration=duration,
        frame_interval=interval,
        frames=frames,
        full_transcript=full_transcript,
        transcript_segments=segments,
    )


def process_videos_parallel(
    video_items: list[tuple[str, bytes]],
    max_workers: int = 4,
    progress_callback=None,
) -> dict[str, ProcessedVideo]:
    """Process multiple videos in parallel (ffmpeg + Whisper are I/O bound).

    Args:
        video_items: List of (filename, video_bytes) tuples
        max_workers: Max concurrent workers
        progress_callback: Optional callback(completed, total, filename)

    Returns:
        Dict mapping filename -> ProcessedVideo
    """
    results: dict[str, ProcessedVideo] = {}
    total = len(video_items)

    with ThreadPoolExecutor(max_workers=min(max_workers, total)) as executor:
        future_to_name = {
            executor.submit(process_video, video_bytes, filename): filename
            for filename, video_bytes in video_items
        }
        for future in as_completed(future_to_name):
            filename = future_to_name[future]
            results[filename] = future.result()
            if progress_callback:
                progress_callback(len(results), total, filename)

    return results

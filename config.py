import os
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Read from os.getenv first, then fall back to st.secrets (Streamlit Cloud)."""
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY")
SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_KEY")

ADMIN_PASSWORD = _get_secret("ADMIN_PASSWORD")

CLAUDE_MODEL = "claude-sonnet-4-20250514"

# 영상 프레임 추출 설정
FRAME_INTERVAL_SHORT = 0.8   # 20초 미만 영상: 0.8초 간격
FRAME_INTERVAL_LONG = 1.5    # 20초 이상 영상: 1.5초 간격
SHORT_VIDEO_THRESHOLD = 20.0 # 짧은 영상 기준 (초)

# PDF 이미지 변환 DPI
PDF_DPI = 200

# 프레임 이미지 최대 크기 (Claude API 전송용)
MAX_IMAGE_WIDTH = 1024
MAX_IMAGE_HEIGHT = 1024

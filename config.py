import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

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

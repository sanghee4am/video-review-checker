FROM python:3.11-slim

# 시스템 패키지 (ffmpeg 필수)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 먼저 설치 (캐시 활용)
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# 소스 복사
COPY . .

EXPOSE 3003

CMD ["uvicorn", "api_main:app", "--host", "0.0.0.0", "--port", "3003"]

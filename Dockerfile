# =============================================================================
# Stage 1: Builder - 의존성 설치 및 휠 빌드
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# 빌드 도구 설치 (일부 패키지 컴파일에 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# 의존성 파일 복사
COPY requirements.txt .

# 의존성 휠 빌드
RUN pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt

# =============================================================================
# Stage 2: Runtime - 경량 실행 이미지
# =============================================================================
FROM python:3.11-slim

# 보안: non-root 유저로 실행
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

# 런타임 라이브러리만 설치 (lxml 등에 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Builder에서 빌드한 휠 복사 및 설치
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# 애플리케이션 코드 복사
COPY app ./app

# 로그 디렉토리 생성 (non-root 유저가 쓸 수 있도록)
RUN mkdir -p /app/logs

# 소유권 변경 (app 및 logs 디렉토리 포함)
RUN chown -R appuser:appgroup /app

# non-root 유저로 전환
USER appuser

# Cloud Run은 PORT 환경변수를 사용 (기본값 8080)
ENV PORT=8080

# Python 출력 버퍼링 비활성화 (실시간 로그, 크래시 시 로그 유실 방지)
ENV PYTHONUNBUFFERED=1

# Health check (선택적)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/ping')" || exit 1

# Cloud Run 요구사항: 0.0.0.0 바인딩, $PORT 동적 감지
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

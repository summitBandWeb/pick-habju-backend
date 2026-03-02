from prometheus_client import Counter, Histogram
import os

# 환경 변수로 메트릭 비활성화 가능 (테스트 환경 등)
ENABLE_METRICS = os.getenv("ENABLE_METRICS", "true").lower() == "true"

# HTTP 요청 횟수 카운터
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "path", "status_code"]
)

# HTTP 요청 처리 시간 히스토그램 (초 단위)
# 버킷 타겟: 0.1s, 0.5s, 1s, 2s, 5s 등 구간별 요청 수
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path", "status_code"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf"))
)

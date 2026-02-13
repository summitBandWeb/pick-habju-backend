import contextvars
from typing import Optional

# Request ID 또는 Trace ID를 전역적으로 추적하기 위한 ContextVar
# Rationale: 로깅 시 매번 request 객체를 전달하지 않고도 현재 요청의 Trace ID를 식별하기 위해 사용합니다.
trace_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default=None)

def get_trace_id() -> Optional[str]:
    """현재 컨텍스트의 Trace ID를 반환합니다."""
    return trace_id_context.get()

def set_trace_id(trace_id: str) -> None:
    """현재 컨텍스트에 Trace ID를 설정합니다."""
    trace_id_context.set(trace_id)

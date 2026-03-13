import time
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("app")

class AvailabilityCache:
    """합주실 예약 가능 여부 조회를 위한 인메모리 TTL 캐시
    
    외부 API(Naver, Dream 등) 크롤링은 속도가 느리고 호출 제한이 있으므로,
    짧은 시간(60초) 동안 결과를 캐싱하여 동시 접속 시의 서버 부하를 방지합니다.
    """
    
    def __init__(self, ttl_seconds: int = 60):
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._ttl = ttl_seconds
        logger.info(f"[AvailabilityCache] initialized with TTL={ttl_seconds}s")

    def _get_key(self, date: str, start_hour: str, end_hour: str, biz_item_id: str) -> str:
        """캐시 키 생성: 날짜, 시간대, 특정 룸 ID 조합"""
        return f"{date}|{start_hour}-{end_hour}|{biz_item_id}"

    def get(self, date: str, start_hour: str, end_hour: str, biz_item_id: str) -> Optional[Any]:
        """캐시에서 결과를 조회합니다. 만료된 경우 삭제하고 None을 반환합니다."""
        key = self._get_key(date, start_hour, end_hour, biz_item_id)
        if key not in self._cache:
            return None
        
        expiry, data = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None
            
        return data

    def set(self, date: str, start_hour: str, end_hour: str, biz_item_id: str, data: Any):
        """결과를 캐시에 저장합니다."""
        key = self._get_key(date, start_hour, end_hour, biz_item_id)
        expiry = time.time() + self._ttl
        self._cache[key] = (expiry, data)

    def clear(self):
        """캐시 전체를 초기화합니다."""
        self._cache.clear()
        
    def cleanup(self):
        """만료된 항목들을 일괄 정리합니다. (메모리 관리용)"""
        now = time.time()
        expired_keys = [k for k, (exp, _) in self._cache.items() if now > exp]
        for k in expired_keys:
            del self._cache[k]
        if expired_keys:
            logger.debug(f"[AvailabilityCache] cleaned up {len(expired_keys)} expired items")

# 싱글톤 인스턴스 제공
availability_cache = AvailabilityCache(ttl_seconds=60)

import time
import logging
import asyncio
import os
import copy
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("app")

class AvailabilityCache:
    """합주실 예약 가능 여부 조회를 위한 인메모리 TTL 캐시
    
    외부 API(Naver, Dream 등) 크롤링은 속도가 느리고 호출 제한이 있으므로,
    짧은 시간(60초) 동안 결과를 캐싱하여 동시 접속 시의 서버 부하를 방지합니다.
    """
    
    def __init__(self, ttl_seconds: Optional[int] = None):
        if ttl_seconds is None:
            ttl_seconds = int(os.getenv("AVAILABILITY_CACHE_TTL_SECONDS", "60"))
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._inflight: Dict[str, asyncio.Future] = {}
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
            
        return copy.deepcopy(data)

    async def get_or_compute(self, date: str, start_hour: str, end_hour: str, biz_item_id: str, compute_coro):
        """캐시를 조회하거나, 없으면 계산(compute_coro)을 수행하고 결과를 캐싱합니다.
        동시 요청 시 첫 번째 요청만 수행하고 나머지는 그 결과를 대기합니다. (Cache Stampede 방어)
        """
        key = self._get_key(date, start_hour, end_hour, biz_item_id)
        
        # 1. 캐시 확인
        data = self.get(date, start_hour, end_hour, biz_item_id)
        if data is not None:
            # Rationale: 이미 결과가 존재하여 전달받은 코루틴을 실행할 필요가 없음.
            #            파이썬은 생성된 코루틴이 한번도 await되지 않으면 경고를 발생시키므로 명시적으로 닫아줌.
            if asyncio.iscoroutine(compute_coro):
                compute_coro.close()
            return data
            
        # 2. In-flight(진행 중) 요청 확인
        if key in self._inflight:
            logger.debug(f"[AvailabilityCache] Hit inflight: {key}")
            return await self._inflight[key]
            
        # 3. 내가 수행 담당
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._inflight[key] = future
        
        try:
            logger.debug(f"[AvailabilityCache] Miss - starting computation: {key}")
            # Compute (호출자가 전달한 코루틴 실행)
            result = await compute_coro
            # 캐시 저장 (Future 완료 전 저장하여 후속 get()도 즉시 성공하도록 함)
            self.set(date, start_hour, end_hour, biz_item_id, result)
            if not future.done():
                future.set_result(result)
            return result
        except Exception as e:
            if not future.done():
                future.set_exception(e)
            raise e
        finally:
            # 작업 완료 후 In-flight 목록에서 제거
            if key in self._inflight:
                del self._inflight[key]

    def set(self, date: str, start_hour: str, end_hour: str, biz_item_id: str, data: Any):
        """결과를 캐시에 저장합니다."""
        key = self._get_key(date, start_hour, end_hour, biz_item_id)
        expiry = time.time() + self._ttl
        self._cache[key] = (expiry, copy.deepcopy(data))

    def clear(self):
        """캐시 및 대기열 전체를 초기화합니다."""
        self._cache.clear()
        for fut in self._inflight.values():
            if not fut.done():
                fut.set_exception(Exception("Cache cleared"))
        self._inflight.clear()
        
    def cleanup(self):
        """만료된 항목들을 일괄 정리합니다. (메모리 관리용)"""
        now = time.time()
        expired_keys = [k for k, (exp, _) in self._cache.items() if now > exp]
        for k in expired_keys:
            del self._cache[k]
        if expired_keys:
            logger.debug(f"[AvailabilityCache] cleaned up {len(expired_keys)} expired items")

# 싱글톤 인스턴스 제공
availability_cache = AvailabilityCache()

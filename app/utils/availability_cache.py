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
    180초 동안 결과를 캐싱하여 동시 접속 시의 서버 부하를 방지합니다.
    """
    
    def __init__(self, ttl_seconds: Optional[int] = None):
        if ttl_seconds is None:
            ttl_seconds = int(os.getenv("AVAILABILITY_CACHE_TTL_SECONDS", "180"))
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._inflight: Dict[str, asyncio.Future] = {}
        self._ttl = ttl_seconds
        logger.info(f"[AvailabilityCache] initialized with TTL={ttl_seconds}s")


    def _get_key(self, date: str, start_hour: str, end_hour: str, biz_item_id: str) -> str:
        """캐시 키 생성: 날짜, 시간대, 특정 룸 ID 조합"""
        return f"{date}|{start_hour}-{end_hour}|{biz_item_id}"

    def is_pending(self, date: str, start_hour: str, end_hour: str, biz_item_id: str) -> bool:
        """캐시가 유효하거나 현재 진행 중인 요청이 있으면 True를 반환합니다."""
        if self.get(date, start_hour, end_hour, biz_item_id) is not None:
            return True
        return self._get_key(date, start_hour, end_hour, biz_item_id) in self._inflight

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

    async def get_or_compute(self, date: str, start_hour: str, end_hour: str, biz_item_id: str, compute_factory):
        """캐시를 조회하거나, 없으면 factory를 호출하여 계산하고 결과를 캐싱합니다.
        동시 요청 시 첫 번째 요청만 수행하고 나머지는 그 결과를 대기합니다. (Cache Stampede 방어)

        Args:
            compute_factory: 캐시 미스 시에만 호출되는 zero-arg callable.
                             코루틴을 반환해야 한다 (예: lambda: room_compute_wrapper(biz_id)).
                             캐시 히트/인플라이트 시에는 호출되지 않으므로 불필요한 코루틴 생성이 없다.
        """
        key = self._get_key(date, start_hour, end_hour, biz_item_id)

        # 1. 캐시 확인
        data = self.get(date, start_hour, end_hour, biz_item_id)
        if data is not None:
            return data

        # 2. In-flight(진행 중) 요청 확인
        if key in self._inflight:
            logger.debug(f"[AvailabilityCache] Hit inflight: {key}")
            return await self._inflight[key]

        # 3. 내가 수행 담당
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._inflight[key] = future

        try:
            logger.debug(f"[AvailabilityCache] Miss - starting computation: {key}")
            # factory를 캐시 미스 시점에만 호출하여 코루틴 생성
            result = await compute_factory()
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
        
    def incremental_cleanup(self, batch_size: int):
        """매칭된 batch_size만큼의 키를 검사하여 만료된 항목을 제거합니다.
        
        Rationale: 전체 캐시를 한 번에 정리하는 것은 O(N) 비용이 발생하여 
                  요청 응답 시간에 영향을 줄 수 있습니다. 점진적 정리를 통해 
                  비용을 여러 요청에 분산시킵니다.
        """
        if not self._cache:
            return

        now = time.time()
        keys = list(self._cache.keys())
        
        # NOTE: 인스턴스 변수로 현재 인덱스를 관리하여 매 호출마다 다른 범위를 검사할 수도 있으나,
        #       여기서는 단순하게 랜덤 샘플링하거나 앞에서부터 batch_size만큼 확인하는 방식을 취함.
        #       순차적 순회를 위해 간단한 필드를 추가함.
        if not hasattr(self, "_cleanup_idx"):
            self._cleanup_idx = 0
            
        start_idx = self._cleanup_idx % len(keys)
        targets = [keys[(start_idx + i) % len(keys)] for i in range(min(batch_size, len(keys)))]
        
        removed_count = 0
        for k in targets:
            if k in self._cache:
                expiry, _ = self._cache[k]
                if now > expiry:
                    del self._cache[k]
                    removed_count += 1
        
        self._cleanup_idx = (start_idx + len(targets)) % len(keys)
        
        if removed_count > 0:
            logger.debug(f"[AvailabilityCache] incremental cleanup removed {removed_count} items")

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

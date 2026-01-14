from __future__ import annotations
from threading import Lock
from app.crawler.base import BaseCrawler

class CrawlerRegistry:
    """크롤러를 중앙에서 관리하는 싱글톤 레지스트리.

    Thread-safe한 싱글톤 패턴을 사용하여 애플리케이션 전체에서
    단일 레지스트리 인스턴스만 사용하도록 보장합니다.

    Double-checked locking 패턴을 사용하여:
    - 멀티스레드 환경에서 안전하게 동작
    - 불필요한 Lock 획득 최소화 (성능 최적화)
    """
    _instance: CrawlerRegistry | None = None
    _lock: Lock = Lock()

    def __new__(cls):
        # 첫 번째 체크: Lock 없이 빠르게 확인 (대부분의 경우)
        if cls._instance is None:
            with cls._lock:
                # 두 번째 체크: Lock 내에서 다시 확인 (thread-safe)
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # 인스턴스 변수로 초기화 (클래스 변수 공유 방지)
                    cls._instance._crawlers = {}
        return cls._instance

    def register(self, name: str, crawler: BaseCrawler):
        """크롤러를 레지스트리에 등록.

        Args:
            name: 크롤러 타입 이름 (예: "dream", "groove", "naver")
            crawler: BaseCrawler를 상속받은 크롤러 인스턴스
        """
        self._crawlers[name] = crawler

    def get(self, name: str) -> BaseCrawler:
        """이름으로 크롤러 조회.

        Args:
            name: 조회할 크롤러 타입 이름

        Returns:
            해당 크롤러 인스턴스, 없으면 None
        """
        return self._crawlers.get(name)

    def get_all(self) -> list[BaseCrawler]:
        """등록된 모든 크롤러 인스턴스 리스트 반환.

        Returns:
            크롤러 인스턴스 리스트
        """
        return list(self._crawlers.values())

    def get_all_map(self) -> dict[str, BaseCrawler]:
        """등록된 크롤러 맵 복사본 반환.

        Returns:
            크롤러 타입을 키로, 크롤러 인스턴스를 값으로 하는 딕셔너리 복사본

        Note:
            원본 맵 수정을 방지하기 위해 복사본을 반환합니다.
        """
        return self._crawlers.copy()

    # Alias for backward compatibility
    def get_all_as_dict(self) -> dict[str, BaseCrawler]:
        """get_all_map의 별칭 (하위 호환성 유지)."""
        return self.get_all_map()

# Global singleton instance
registry = CrawlerRegistry()

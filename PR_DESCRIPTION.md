# 🎯 네이버 합주실 데이터 수집 모듈

## 개요
네이버 지도에서 합주실 정보를 자동으로 수집하고 LLM으로 파싱하여 데이터베이스에 저장하는 기능을 구현했습니다.

## 주요 변경사항

### ✨ 새 기능
- **NaverMapCrawler**: Playwright 기반 네이버 지도 크롤러 (Stealth 모드 적용)
- **NaverRoomFetcher**: GraphQL API를 통한 상세 정보 수집
- **RoomParserService**: Ollama LLM을 활용한 비정형 텍스트 파싱 (llama3.1)
- **RoomCollectionService**: 전체 흐름 관리 (Orchestrator)
- **전국 자동 수집**: 서울 25개 구 + 주요 광역시 지역 크롤링

### 🔧 최적화
- LLM 배치 처리 동시성 적용 (5개 × 3배치 = 15개 병렬 처리)
- 파싱 실패 시 기본값 100 설정 (수동 검토 플래그)
- Ollama 로컬 LLM 사용 (`llama3.1` 8B 모델)

### 🐛 버그 수정
- Naver headless 브라우저 감지 우회 (Stealth 조치)
- Windows asyncio 호환성 개선 (`sync_playwright` + `ThreadPoolExecutor`)
- API 테스트 `ApiResponse` 엔벨롭 패턴 적용

## 관련 파일

| 경로 | 설명 |
|------|------|
| `app/crawler/naver_map_crawler.py` | 네이버 지도 검색 크롤러 |
| `app/crawler/naver_room_fetcher.py` | GraphQL 상세 정보 수집 |
| `app/services/room_parser_service.py` | LLM 텍스트 파싱 |
| `app/services/room_collection_service.py` | 수집 흐름 관리 |
| `scripts/collect_rooms.py` | CLI 실행 스크립트 |
| `docs/naver-room-crawler.md` | **📖 시스템 설명 문서** -> 차후 맥락파악 시 삭제하고 노션으로 옮길 예정입니다. |

## 사용 방법

```bash
python scripts/collect_rooms.py --auto
```

## 테스트 결과

- ✅ `tests/services/` - 9개 통과
- ✅ `tests/crawler/` - 통과
- ✅ `tests/integration/` - 통과

## 향후 작업 (별도 이슈)

- [ ] PostGIS 공간 인덱스 적용 (위치 기반 검색 최적화)
- [ ] 지역 컬럼 추가 및 인덱싱
- [ ] 스케줄링 자동 수집

---

**Closes #106**

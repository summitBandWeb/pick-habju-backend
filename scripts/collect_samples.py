"""
크롤링 원본 데이터 수집 스크립트

실제 크롤링 데이터를 수집하여 패턴 분석 기초 자료로 사용합니다.
수집된 데이터는 scripts/sample_data/ 디렉토리에 JSON으로 저장됩니다.

사용법:
    python scripts/collect_samples.py --query "홍대 합주실"
    python scripts/collect_samples.py --id 522011
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.crawler.naver_room_fetcher import NaverRoomFetcher
from app.crawler.naver_map_crawler import NaverMapCrawler


async def collect_by_id(business_id: str) -> dict:
    """단일 합주실 정보 수집"""
    fetcher = NaverRoomFetcher()
    result = await fetcher.fetch_full_info(business_id)
    
    if not result:
        print(f"❌ 데이터를 가져올 수 없습니다: {business_id}")
        return None
    
    # 분석용 데이터 정리
    sample = {
        "business_id": business_id,
        "business_name": result["business"].get("businessDisplayName", "N/A"),
        "crawled_at": datetime.now().isoformat(),
        "rooms": []
    }
    
    for room in result.get("rooms", []):
        room_data = {
            "biz_item_id": room.get("bizItemId"),
            "raw_name": room.get("name", ""),
            "raw_desc": room.get("desc", ""),
            "min_price": room.get("minMaxPrice", {}).get("minPrice") if room.get("minMaxPrice") else None,
            "max_price": room.get("minMaxPrice", {}).get("maxNormalPrice") if room.get("minMaxPrice") else None,
            "image_count": len(room.get("bizItemResources", [])),
            # 분석 메타데이터
            "has_desc": bool(room.get("desc")),
            "has_price": room.get("minMaxPrice") is not None,
            "name_has_tag": any(tag in room.get("name", "") for tag in ["[", "(", "평일", "주말"])
        }
        sample["rooms"].append(room_data)
    
    return sample


async def collect_by_query(query: str, limit: int = 10) -> list:
    """검색어로 여러 합주실 수집"""
    crawler = NaverMapCrawler()
    results = await crawler.search_rehearsal_rooms(query)
    
    if not results:
        print(f"❌ 검색 결과가 없습니다: {query}")
        return []
    
    # 제한 적용
    results = results[:limit]
    print(f"📍 {len(results)}개 합주실 수집 시작...")
    
    samples = []
    for i, item in enumerate(results, 1):
        business_id = item.get("id")
        print(f"  [{i}/{len(results)}] {item.get('name', 'N/A')} ({business_id})")
        
        sample = await collect_by_id(business_id)
        if sample:
            samples.append(sample)
        
        # Rate limiting
        await asyncio.sleep(0.5)
    
    return samples


def save_samples(samples: list, filename: str):
    """수집 결과를 JSON 파일로 저장"""
    output_dir = Path(__file__).parent / "sample_data"
    output_dir.mkdir(exist_ok=True)
    
    output_path = output_dir / filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 저장 완료: {output_path}")
    print(f"   총 {len(samples)}개 합주실, {sum(len(s['rooms']) for s in samples)}개 룸")


def print_summary(samples: list):
    """수집 결과 요약 출력"""
    total_rooms = sum(len(s["rooms"]) for s in samples)
    rooms_with_desc = sum(1 for s in samples for r in s["rooms"] if r["has_desc"])
    rooms_with_price = sum(1 for s in samples for r in s["rooms"] if r["has_price"])
    rooms_with_tag = sum(1 for s in samples for r in s["rooms"] if r["name_has_tag"])
    
    print("\n" + "=" * 50)
    print("📊 수집 요약")
    print("=" * 50)
    print(f"합주실 수: {len(samples)}")
    print(f"총 룸 수: {total_rooms}")
    print(f"desc 있음: {rooms_with_desc} ({rooms_with_desc/total_rooms*100:.1f}%)")
    print(f"가격 있음: {rooms_with_price} ({rooms_with_price/total_rooms*100:.1f}%)")
    print(f"이름에 태그: {rooms_with_tag} ({rooms_with_tag/total_rooms*100:.1f}%)")
    print("=" * 50)


async def main():
    parser = argparse.ArgumentParser(description="크롤링 원본 데이터 수집")
    parser.add_argument("--query", type=str, help="검색어 (예: 홍대 합주실)")
    parser.add_argument("--id", type=str, help="특정 business_id")
    parser.add_argument("--limit", type=int, default=10, help="수집 개수 제한")
    parser.add_argument("--output", type=str, help="출력 파일명")
    
    args = parser.parse_args()
    
    if not args.query and not args.id:
        parser.print_help()
        return
    
    samples = []
    
    if args.id:
        sample = await collect_by_id(args.id)
        if sample:
            samples.append(sample)
    elif args.query:
        samples = await collect_by_query(args.query, args.limit)
    
    if samples:
        # 파일명 생성
        filename = args.output or f"sample_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_samples(samples, filename)
        print_summary(samples)


if __name__ == "__main__":
    asyncio.run(main())

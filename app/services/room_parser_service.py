import os
import json
import logging
import asyncio
import google.generativeai as genai
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class RoomParserService:
    """LLM을 사용하여 비정형 룸 정보를 구조화된 데이터로 변환합니다."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. LLM parsing will fail.")
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def parse_room_desc(self, name: str, desc: str) -> Dict[str, Any]:
        """룸 이름과 설명을 기반으로 구조화된 정보를 추출합니다."""
        if not self.api_key:
            return {}

        prompt = f"""
        다음 합주실 정보에서 데이터를 추출하여 JSON으로 반환해주세요.
        값이 없거나 불확실하면 null로 표기하세요.

        [입력 정보]
        룸 이름: {name}
        설명: {desc or "내용 없음"}

        [추출 규칙]
        1. clean_name: "[평일]", "(주말)" 등 태그를 제거한 순수 룸 이름 (예: "[평일] 블랙룸" -> "블랙룸")
        2. day_type: 이름에 "평일"이 있으면 "weekday", "주말/공휴일"이 있으면 "weekend", 없으면 null
        3. max_capacity: 최대 수용 인원 (숫자)
        4. recommend_capacity: 권장 인원 (숫자). 범위(4~6)인 경우 중간값(5).
        5. base_capacity: 추가 요금 기준이 되는 기본 인원 (숫자). "1인 추가시" 같은 문구가 있으면 해당 기준 인원.
        6. extra_charge: 인원 초과 시 1인당/시간당 추가 요금 (숫자).
        7. requires_call_on_same_day: "당일 예약은 전화" 같은 문구가 있으면 true (boolean)

        [응답 형식]
        {{
            "clean_name": "...",
            "day_type": "...",
            "max_capacity": 0,
            "recommend_capacity": 0,
            "base_capacity": 0,
            "extra_charge": 0,
            "requires_call_on_same_day": false
        }}
        """
        
        try:
            # 비동기 실행을 위해 run_in_executor 사용 (google-generativeai는 동기 라이브러리)
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, self.model.generate_content, prompt)
            
            # JSON 파싱 (마크다운 코드블록 제거 처리)
            text = response.text
            if text.startswith("```json"):
                text = text.replace("```json", "").replace("```", "")
            elif text.startswith("```"):
                text = text.replace("```", "")
                
            return json.loads(text.strip())
            
        except Exception as e:
            logger.error(f"LLM parsing failed for {name}: {e}")
            return {
                "clean_name": name,
                "day_type": None,
                "max_capacity": 1,
                "recommend_capacity": 1,
                "base_capacity": None,
                "extra_charge": None,
                "requires_call_on_same_day": False
            }

    def merge_weekday_weekend_rooms(self, rooms_data: List[Dict]) -> List[Dict]:
        """
        평일/주말이 분리된 룸 데이터를 하나로 병합합니다.
        
        Args:
            rooms_data: API 크롤링 결과(raw bizItems)에 LLM 파싱 결과가 합쳐진 딕셔너리 리스트
                       (raw data + parsed fields)
        """
        merged = {}
        
        for room in rooms_data:
            # LLM 파싱된 이름 사용 (없으면 원래 이름)
            clean_name = room.get("clean_name", room["name"]).strip()
            
            if clean_name not in merged:
                merged[clean_name] = {
                    "name": clean_name,
                    # 공통 정보 (첫 번째 발견된 항목 기준)
                    "max_capacity": room.get("max_capacity", 1),
                    "recommend_capacity": room.get("recommend_capacity", 1),
                    "base_capacity": room.get("base_capacity"),
                    "extra_charge": room.get("extra_charge"),
                    "requires_call_on_same_day": room.get("requires_call_on_same_day", False),
                    "image_urls": [r["resourceUrl"] for r in room.get("bizItemResources", [])],
                    # ID 및 가격 초기화
                    "biz_item_id": None, # 구분 없는 경우
                    "price_per_hour": 0,    # 구분 없는 경우
                    # 평일/주말 슬롯
                    "weekday": None,
                    "weekend": None
                }
            
            target = merged[clean_name]
            day_type = room.get("day_type")
            price = room.get("minMaxPrice", {}).get("minPrice", 0)
            
            if day_type == "weekday":
                target["weekday"] = {
                    "id": room["bizItemId"],
                    "price": price
                }
            elif day_type == "weekend":
                target["weekend"] = {
                    "id": room["bizItemId"],
                    "price": price
                }
            else:
                # 구분 없는 경우 (기본값)
                target["biz_item_id"] = room["bizItemId"]
                target["price_per_hour"] = price

        # 최종 리스트 변환 및 평일/주말 데이터 평탄화
        final_list = []
        for name, data in merged.items():
            # 평일 데이터가 있으면 그것을 기본으로, 없으면 주말, 둘다 없으면 기본
            # DB 스키마에는 biz_item_id가 PK이므로, 하나를 메인으로 선택해야 함.
            # 정책: 평일 ID를 메인 biz_item_id로 사용 (없으면 주말, 없으면 일반)
            # 단, 이 경우 주말 ID는 DB에 저장이 안되나? 
            # -> DB 스키마 수정 없이 하려면, 사실 두 레코드로 넣거나 
            #    하나의 Room에 weekday_id, weekend_id 컬럼을 추가해야 했음.
            #    하지만 현재 DB 스키마(Branch, Room)는 biz_item_id가 PK임.
            #    
            #    [중요] 사용자가 제공한 스키마는:
            #    CREATE TABLE room (
            #       biz_item_id VARCHAR(50) NOT NULL, ... PK
            #       price_per_hour ...
            #    )
            #    즉, 평일/주말을 별도 room row로 저장해야 하는 구조임.
            #    'merge'를 해서 하나의 row로 만들 수 없음 (컬럼이 없음).
            #    
            #    따라서 여기서 merge를 하면 안되고, 대신 Grouping ID 정도만 부여하거나
            #    DB 저장 시 별도 Row로 저장하되, 프론트에서 합치도록 해야 함.
            #    
            #    하지만 기획에서는 백엔드가 날짜에 따라 ID를 준다고 했음.
            #    그렇다면 DB에는 2개의 Row가 들어가고, 조회 시 이름을 그룹핑해서 보여줘야 함.
            
            #    Parsing Service는 데이터를 '정제'하는 역할만 하고,
            #    Group merge는 조회 로직(Repository/Service)에서 하는 게 맞음.
            
            pass 

        # [수정] 위 주석대로, DB 스키마가 평일/주말 컬럼이 없으므로
        # 여기서는 단순히 LLM 파싱 결과만 덧붙여서 리턴하고,
        # 저장은 각각의 Row로 하게 둠.
        return rooms_data

# 테스트
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service = RoomParserService()
    
    # Mock desc
    desc = "블랙룸 (4~6인 권장, 최대 10명). 기본 4인, 1인 추가시 3000원. 당일 예약은 전화 문의 바람."
    result = asyncio.run(service.parse_room_desc("[평일] 블랙룸", desc))
    print(json.dumps(result, indent=2, ensure_ascii=False))

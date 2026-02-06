"""
룸 정보 파싱 서비스

Ollama 로컬 LLM을 사용하여 비정형 합주실 정보를 구조화된 데이터로 변환합니다.
LLM 파싱 실패 시 정규표현식 기반 Fallback으로 안정성을 보장합니다.

사용법:
    service = RoomParserService()
    result = await service.parse_room_desc("[평일] 블랙룸", "최대 10인")
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional

from app.core.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


# 8B 모델 최적화 프롬프트 (Few-shot 예시 포함)
ROOM_PARSE_PROMPT = """Extract room info as JSON.

Example 1:
Input: "[평일] 블랙룸", "최대 8명, 4~6인 권장"
Output: {{"clean_name": "블랙룸", "day_type": "weekday", "max_capacity": 8, "recommend_capacity": 5, "base_capacity": null, "extra_charge": null, "requires_call_on_same_day": false}}

Example 2:
Input: "화이트룸", "기본 4인, 인당 3000원 추가"
Output: {{"clean_name": "화이트룸", "day_type": null, "max_capacity": null, "recommend_capacity": null, "base_capacity": 4, "extra_charge": 3000, "requires_call_on_same_day": false}}

Example 3:
Input: "[주말] 스튜디오A", "당일 예약은 전화 문의"
Output: {{"clean_name": "스튜디오A", "day_type": "weekend", "max_capacity": null, "recommend_capacity": null, "base_capacity": null, "extra_charge": null, "requires_call_on_same_day": true}}

Rules:
- clean_name: Remove tags like [평일], (주말) from name
- day_type: "weekday" if 평일, "weekend" if 주말/공휴일, else null
- max_capacity: Max people (number)
- recommend_capacity: Recommended people. Use mid-value for ranges (4~6 -> 5)
- base_capacity: Base people count for pricing
- extra_charge: Extra charge per person (number only, no currency)
- requires_call_on_same_day: true if "당일" and ("전화" or "문의") found

Now extract:
Input: "{name}", "{desc}"
Output:"""


# 배치 파싱용 프롬프트
BATCH_PARSE_PROMPT = """Extract room info from multiple rooms as JSON object.
Keys should be the room IDs provided. Use null for missing values.

Rules:
- clean_name: Remove tags like [평일], (주말) from name
- day_type: "weekday" if 평일, "weekend" if 주말/공휴일, else null
- max_capacity: Max people (number)
- recommend_capacity: Use mid-value for ranges (4~6 -> 5)
- base_capacity: Base people count for pricing
- extra_charge: Extra charge per person (number only)
- requires_call_on_same_day: true if "당일" and ("전화" or "문의") found

Rooms:
{rooms_text}

Output format:
{{"id1": {{"clean_name": "...", "day_type": "...", ...}}, "id2": {{...}}}}"""


class RoomParserService:
    """Ollama 로컬 LLM을 사용하여 비정형 룸 정보를 구조화된 데이터로 변환합니다.
    
    LLM 파싱 실패 시 정규표현식 기반 Fallback을 사용하여 안정성을 보장합니다.
    8B 소형 모델의 특성을 고려한 Few-shot 프롬프트를 사용합니다.
    """
    
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        """RoomParserService 초기화.
        
        Args:
            ollama_client: Ollama 클라이언트 인스턴스 (DI용)
        """
        self.ollama_client = ollama_client or OllamaClient()

    async def parse_room_desc(self, name: str, desc: str) -> Dict[str, Any]:
        """룸 이름과 설명을 기반으로 구조화된 정보를 추출합니다.
        
        Args:
            name: 룸 이름 (예: "[평일] 블랙룸")
            desc: 룸 설명 (예: "최대 10인, 4~6인 권장")
            
        Returns:
            파싱된 룸 정보 딕셔너리
        """
        prompt = ROOM_PARSE_PROMPT.format(
            name=name,
            desc=desc or "내용 없음"
        )
        
        # Ollama LLM 파싱 시도
        response = await self.ollama_client.generate(prompt)
        
        if response:
            try:
                result = self._extract_json_from_response(response)
                parsed = json.loads(result)
                
                # 파싱 결과 검증
                if self._validate_parsed_result(parsed):
                    return parsed
                    
                logger.warning(f"파싱 결과 검증 실패 for {name}. Fallback to Regex.")
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 파싱 실패 for {name}: {e}. Fallback to Regex.")
        
        # Fallback: 정규표현식 파싱
        return self._parse_with_regex(name, desc)

    def _extract_json_from_response(self, text: str) -> str:
        """LLM 응답에서 JSON 부분만 추출 (마크다운 코드블록 제거)."""
        text = text.strip()

        # ```json ... ``` 형태
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        return text.strip()
    
    def _validate_parsed_result(self, result: Dict[str, Any]) -> bool:
        """파싱 결과의 유효성을 검증합니다.
        
        8B 모델은 오류율이 높으므로 현실적 범위를 검증합니다.
        
        Args:
            result: 파싱된 결과 딕셔너리
            
        Returns:
            유효하면 True, 아니면 False
        """
        # 1. 필수 필드 존재 확인
        if "clean_name" not in result:
            return False
        
        # 2. 최대 수용 인원 범위 검증 (합주실 현실적 범위: 1~50명)
        max_cap = result.get("max_capacity")
        if max_cap is not None:
            if not isinstance(max_cap, (int, float)) or max_cap < 1 or max_cap > 50:
                return False
        
        # 3. 권장 인원 범위 검증
        rec_cap = result.get("recommend_capacity")
        if rec_cap is not None:
            if not isinstance(rec_cap, (int, float)) or rec_cap < 1 or rec_cap > 50:
                return False
        
        # 4. 추가 요금 범위 검증 (0~50,000원)
        extra = result.get("extra_charge")
        if extra is not None:
            if not isinstance(extra, (int, float)) or extra < 0 or extra > 50000:
                return False
        
        # 5. day_type 값 검증
        day_type = result.get("day_type")
        if day_type is not None and day_type not in ["weekday", "weekend"]:
            return False
        
        return True

    def _parse_with_regex(self, name: str, desc: str) -> Dict[str, Any]:
        """정규표현식을 사용한 Fallback 파싱 로직.
        
        LLM 파싱 실패 시 사용되는 안정적인 Fallback입니다.
        """
        desc = desc or ""
        
        # 1. clean_name & day_type
        clean_name = name
        day_type = None
        
        if "[평일]" in name or "(평일)" in name:
            day_type = "weekday"
            clean_name = re.sub(r'\[평일\]|\(평일\)', '', clean_name).strip()
        elif "[주말]" in name or "(주말)" in name or "주말/공휴일" in name:
            day_type = "weekend"
            clean_name = re.sub(r'\[주말[^\]]*\]|\(주말[^)]*\)|\[주말/공휴일\]', '', clean_name).strip()
            
        # 2. Capacity (최대 N인, N~M인)
        max_cap = None
        rec_cap = None

        # "최대 10인", "최대 10명", "Max 10명", "10인까지 가능"
        max_match = re.search(r'(?:최대|max|MAX)\s*(\d+)', desc, re.IGNORECASE)
        if max_match:
            max_cap = int(max_match.group(1))
        else:
            # "10인까지", "10명까지 가능" 패턴
            until_match = re.search(r'(\d+)\s*(?:인|명)\s*(?:까지|수용)', desc)
            if until_match:
                max_cap = int(until_match.group(1))

        # "N~M인", "N~M명" -> 권장 인원 (중간값)
        range_match = re.search(r'(\d+)\s*[~\-]\s*(\d+)\s*(?:인|명)?', desc)
        if range_match:
            min_r = int(range_match.group(1))
            max_r = int(range_match.group(2))
            rec_cap = (min_r + max_r) // 2
            # 최대 인원을 못 찾았으면 범위의 최댓값 사용
            if not max_cap:
                max_cap = max_r
        elif max_cap and max_cap > 1:
            rec_cap = max_cap // 2 if max_cap > 4 else max_cap
            
        # 3. Base Capacity & Extra Charge
        base_cap = None
        extra_charge = None
        
        # "기본 4인"
        base_match = re.search(r'기본\s*(\d+)', desc)
        if base_match:
            base_cap = int(base_match.group(1))
            
        # "1인 추가시 3000원", "인당 3000원"
        charge_match = re.search(r'(?:1인|인당)\s*(?:추가)?.*?(\d+(?:,\d+)?)\s*원', desc)
        if charge_match:
            extra_charge = int(charge_match.group(1).replace(',', ''))
            
        # 4. Same day call
        requires_call = "당일" in desc and ("전화" in desc or "문의" in desc)
        
        return {
            "clean_name": clean_name,
            "day_type": day_type,
            "max_capacity": max_cap,
            "recommend_capacity": rec_cap,
            "base_capacity": base_cap,
            "extra_charge": extra_charge,
            "requires_call_on_same_day": requires_call
        }

    async def parse_room_desc_batch(self, items: List[Dict]) -> Dict[str, Dict]:
        """여러 룸 정보를 한 번에 파싱합니다.
        
        배치 처리로 API 호출 횟수를 줄여 효율성을 높입니다.
        
        Args:
            items: [{"id": "...", "name": "...", "desc": "..."}] 형태의 리스트
            
        Returns:
            {"id": {파싱결과}, ...}
        """
        if not items:
            return {}
        
        # 프롬프트 구성
        rooms_text_parts = []
        for item in items:
            rooms_text_parts.append(
                f"ID: {item['id']}\nName: {item['name']}\nDesc: {item.get('desc') or ''}\n---"
            )
        
        prompt = BATCH_PARSE_PROMPT.format(rooms_text="\n".join(rooms_text_parts))
        
        # Ollama LLM 파싱 시도
        response = await self.ollama_client.generate(prompt, max_tokens=1024)
        
        if response:
            try:
                text = self._extract_json_from_response(response)
                parsed_results = json.loads(text)
                
                # 각 아이템별로 검증, 실패 시 Regex Fallback
                final_results = {}
                for item in items:
                    rid = item["id"]
                    data = parsed_results.get(rid)
                    if data and self._validate_parsed_result(data):
                        final_results[rid] = data
                    else:
                        logger.warning(f"배치 파싱 검증 실패: {rid}, Regex fallback 사용.")
                        final_results[rid] = self._parse_with_regex(item["name"], item["desc"])
                        
                return final_results
                
            except json.JSONDecodeError as e:
                logger.warning(f"배치 JSON 파싱 실패: {e}. 전체 Regex fallback.")
        
        # Fallback: 모든 아이템을 Regex로 파싱
        return {
            item["id"]: self._parse_with_regex(item["name"], item["desc"]) 
            for item in items
        }

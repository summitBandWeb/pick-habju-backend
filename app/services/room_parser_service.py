import os
import json
import logging
import asyncio
import re
import google.generativeai as genai
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Gemini 무료 플랜 Rate Limiting (15 RPM)
GEMINI_RATE_LIMIT_SECONDS = 4

class RoomParserService:
    """LLM(Gemini)을 사용하여 비정형 룸 정보를 구조화된 데이터로 변환합니다."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. LLM parsing will fail.")
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash')


    async def parse_room_desc(self, name: str, desc: str) -> Dict[str, Any]:
        """룸 이름과 설명을 기반으로 구조화된 정보를 추출합니다."""
        if not self.api_key:
            # API Key 없으면 바로 Regex Fallback
            return self._parse_with_regex(name, desc)

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

            # Rate limiting (Gemini 무료 플랜 15 RPM)
            await asyncio.sleep(GEMINI_RATE_LIMIT_SECONDS)

            # JSON 파싱 (마크다운 코드블록 제거 처리)
            text = response.text.strip()
            text = self._extract_json_from_response(text)

            return json.loads(text)
            
        except Exception as e:
            logger.warning(f"LLM parsing failed for {name}: {e}. Falling back to Regex parsing.")
            return self._parse_with_regex(name, desc)

    def _extract_json_from_response(self, text: str) -> str:
        """LLM 응답에서 JSON 부분만 추출 (마크다운 코드블록 제거)"""
        text = text.strip()

        # ```json ... ``` 형태
        if text.startswith("```json"):
            text = text[7:]  # "```json" 제거
        elif text.startswith("```"):
            text = text[3:]  # "```" 제거

        if text.endswith("```"):
            text = text[:-3]  # 끝의 ``` 제거

        return text.strip()

    def _parse_with_regex(self, name: str, desc: str) -> Dict[str, Any]:
        """정규표현식을 사용한 Fallback 파싱 로직"""
        desc = desc or ""
        
        # 1. clean_name & day_type
        clean_name = name
        day_type = None
        
        if "[평일]" in name or "(평일)" in name:
            day_type = "weekday"
            clean_name = re.sub(r'\[평일\]|\(평일\)', '', clean_name).strip()
        elif "[주말]" in name or "(주말)" in name or "주말/공휴일" in name:
            day_type = "weekend"
            clean_name = re.sub(r'\[주말[^]]*\]|\(주말[^)]*\)|\[주말/공휴일\]', '', clean_name).strip()
            
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
            rec_cap = max_cap // 2 if max_cap > 4 else max_cap  # 대략적인 추정
            
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
        """
        여러 룸 정보를 한 번에 파싱합니다.
        
        Args:
            items: [{"id": "...", "name": "...", "desc": "..."}] 형태의 리스트
            
        Returns:
            { "id": {파싱결과}, ... }
        """
        if not items:
            return {}
            
        if not self.api_key:
            return {item["id"]: self._parse_with_regex(item["name"], item["desc"]) for item in items}

        # 프롬프트 구성
        prompt_items = []
        for item in items:
            prompt_items.append(f"ID: {item['id']}\nName: {item['name']}\nDesc: {item.get('desc') or ''}\n---")
            
        prompt_text = "\n".join(prompt_items)
        
        prompt = f"""
        Extract structured data from the following list of rehearsal rooms.
        Return a JSON Object where keys are the 'ID' provided and values are the extracted data.
        Use 'null' for missing or uncertain values.

        [Data List]
        {prompt_text}

        [Extraction Rules]
        1. clean_name: Remove tags like "[Weekday]", "(Weekend)" from name.
        2. day_type: "weekday" if name contains "평일", "weekend" if "주말", else null.
        3. max_capacity: Max people (number).
        4. recommend_capacity: Recommended people (number). Use mid-value for ranges (4~6 -> 5).
        5. base_capacity: Base people count for pricing (number).
        6. extra_charge: Extra charge per person (number).
        7. requires_call_on_same_day: true if "당일" and ("전화" or "문의") found (boolean).

        [Response Format]
        {{
            "id1": {{ "clean_name": "...", "max_capacity": 4, ... }},
            "id2": {{ ... }}
        }}
        """
        
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, self.model.generate_content, prompt)

            # Rate limiting
            await asyncio.sleep(GEMINI_RATE_LIMIT_SECONDS)

            text = response.text.strip()
            return self._process_llm_response(text, items)

        except Exception as e:
            logger.warning(f"Batch LLM parsing failed: {e}. Falling back to Regex.")
            return {item["id"]: self._parse_with_regex(item["name"], item["desc"]) for item in items}

    def _process_llm_response(self, text: str, items: List[Dict]) -> Dict[str, Dict]:
        """LLM 응답 텍스트를 파싱하고 후처리하는 공통 로직"""
        text = self._extract_json_from_response(text)
        try:
            parsed_results = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("JSON Decode Error in LLM response. Fallback to Regex.")
            return {item["id"]: self._parse_with_regex(item["name"], item["desc"]) for item in items}
            
        final_results = {}
        for item in items:
            rid = item["id"]
            data = parsed_results.get(rid)
            if not data:
                logger.warning(f"Batch parsing failed for item {rid}, using regex fallback.")
                final_results[rid] = self._parse_with_regex(item["name"], item["desc"])
            else:
                final_results[rid] = data
        
        return final_results

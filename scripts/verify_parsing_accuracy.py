import asyncio
import json
import os
import httpx
from typing import List, Dict, Any

# Test Data: Diverse room descriptions to challenge the parser
TEST_CASES = [
    {
        "id": "TC01",
        "name": "[평일] 블랙룸",
        "desc": "최대 10인 수용 가능, 시간당 15000원",
        "expected": {"clean_name": "블랙룸", "day_type": "weekday", "max_capacity": 10, "extra_charge": None}
    },
    {
        "id": "TC02",
        "name": "화이트룸 (주말)",
        "desc": "4~6인 권장, 최대 8인. 기본 4인, 1인 추가시 3,000원",
        "expected": {"clean_name": "화이트룸", "day_type": "weekend", "recommend_capacity": 5, "max_capacity": 8, "base_capacity": 4, "extra_charge": 3000}
    },
    {
        "id": "TC03",
        "name": "드럼연습실",
        "desc": "당일 예약은 전화 문의 바랍니다. 010-1234-5678",
        "expected": {"requires_call_on_same_day": True}
    },
    {
        "id": "TC04",
        "name": "일반 합주실",
        "desc": "넓고 쾌적한 공간입니다.",
        "expected": {"max_capacity": None, "recommend_capacity": None} # Should appear as null/None
    },
    {
        "id": "TC05",
        "name": "특실",
        "desc": "인원추가비용 없음. 10명까지.",
        "expected": {"max_capacity": 10, "extra_charge": None}
    }
]

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

async def parse_with_ollama(item: Dict) -> Dict[str, Any]:
    prompt = f"""
    Extract structured data from the rehearsal room info.
    Return ONLY a JSON Object. Use 'null' for missing values.

    Input:
    Name: {item['name']}
    Desc: {item['desc']}

    [Extraction Rules]
    1. clean_name: Remove tags like "[Weekday]", "(Weekend)" from name.
    2. day_type: "weekday" if name contains "평일", "weekend" if "주말", else null.
    3. max_capacity: Max people (number).
    4. recommend_capacity: Recommended people (number). Use mid-value for ranges.
    5. base_capacity: Base people count for pricing (number).
    6. extra_charge: Extra charge per person (number).
    7. requires_call_on_same_day: true if "당일" and ("전화" or "문의") found (boolean).

    Response Format:
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
    
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False
    }
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            text = result.get("response", "")
            return json.loads(text)
    except Exception as e:
        print(f"Error parsing {item['id']}: {e}")
        return {}

async def main():
    print(f"=== Verifying Parsing Accuracy with {OLLAMA_MODEL} ===\n")
    
    results = []
    
    for item in TEST_CASES:
        print(f"Processing {item['id']}...", end=" ", flush=True)
        parsed = await parse_with_ollama(item)
        print("Done.")
        
        # Compare with expected (basic check)
        issues = []
        expected = item["expected"]
        
        for key, val in expected.items():
            parsed_val = parsed.get(key)
            # lax comparison for nulls
            if val is None and parsed_val == 0: continue # Accept 0 as null-ish for numbers maybe? No, let's be strict first.
            
            if parsed_val != val:
                issues.append(f"{key}: Expected {val} != Got {parsed_val}")
        
        results.append({
            "id": item["id"],
            "input": item["name"],
            "parsed": parsed,
            "issues": issues,
            "status": "PASS" if not issues else "FAIL"
        })

    # Report Generation
    print("\n" + "="*50)
    print("ANALYSIS REPORT")
    print("="*50)
    
    fail_count = 0
    for res in results:
        status_icon = "✅" if res['status'] == 'PASS' else "❌"
        print(f"\n{status_icon} [{res['id']}] {res['input']}")
        if res['status'] == 'FAIL':
            fail_count += 1
            print("  [Discrepancies]")
            for issue in res['issues']:
                print(f"   - {issue}")
            print("  [Full Parsed Output]")
            try:
                print(f"   {json.dumps(res['parsed'], ensure_ascii=True)}")
            except Exception:
                print("   (Output contains non-printable characters)")
        else:
             print("  [Perfect Match]")

    print("\n" + "="*50)
    print(f"Total: {len(results)}, Passed: {len(results) - fail_count}, Failed: {fail_count}")

if __name__ == "__main__":
    asyncio.run(main())

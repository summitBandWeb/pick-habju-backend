import asyncio
import json
import httpx

# Configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"

async def test_ollama_json():
    print(f"Testing model: {MODEL_NAME}...")
    
    prompt = """
    Extract info as JSON.
    Input: "Name: [Weekday] Blue Room, Desc: Max 5 people, 10000 won per hour."
    
    Rules:
    - clean_name: remove tags
    - max_capacity: number
    - price: number
    """
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "format": "json",
        "stream": False
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            
            result = response.json()
            generated_text = result.get("response", "")
            
            print("\n[Raw Response]")
            print(generated_text)
            
            try:
                parsed = json.loads(generated_text)
                print("\n[Parsed JSON]")
                print(json.dumps(parsed, indent=2, ensure_ascii=False))
                
                # Validation
                if parsed.get("clean_name") == "Blue Room" and parsed.get("max_capacity") == 5:
                    print("\n✅ Verification SUCCESS: Model understands JSON extraction.")
                    return True
                else:
                    print("\n⚠️ Verification WARNING: JSON parsed but values might be incorrect.")
                    return False
                    
            except json.JSONDecodeError:
                print("\n❌ Verification FAILED: Output is not valid JSON.")
                return False
                
    except Exception as e:
        print(f"\n❌ Connection Error: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_ollama_json())

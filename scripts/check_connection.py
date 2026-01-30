# scripts/check_connection.py
"""
외부 서비스 연동 상태 확인 스크립트 (Health Check)
1. Gemini API (LLM) 연결 및 쿼타 확인
2. Naver 지도 접속 가능 여부 (IP 차단 확인)

실행: python scripts/check_connection.py
"""
import sys
import os
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# .env 로드
load_dotenv()

def check_gemini():
    """Gemini API 연결 테스트"""
    print("\n[1/2] Checking Gemini API Connection...")
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("⚠️ Warning: GEMINI_API_KEY is missing.")
        return False
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content("Say 'Hello' if you can read this.")
        
        if response and response.text:
            print(f"✅ Gemini Connected! Response: {response.text.strip()}")
            return True
        else:
            print("❌ Gemini Connected but returned empty response.")
            return False
            
    except Exception as e:
        print(f"❌ Gemini Connection Failed: {e}")
        return False

def check_naver_access():
    """Naver Map 접속 테스트"""
    print("\n[2/2] Checking Naver Map Access (IP Block Check)...")
    
    status_ok = False
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            target_url = "https://pcmap.place.naver.com/place/list?query=합주실"
            print(f"Connecting to {target_url}...")
            
            response = page.goto(target_url, timeout=10000)
            status = response.status
            
            if status == 200:
                content = page.content()
                if "window.__APOLLO_STATE__" in content:
                    print("✅ Naver Access Successful (Status 200, State Found)")
                    status_ok = True
                else:
                    print("⚠️ Naver Access Limited (Status 200, but no data state found)")
            else:
                print(f"❌ Naver Access Failed with Status: {status}")
            
            browser.close()
                
        except Exception as e:
            print(f"❌ Connection Error: {e}")
            
    return status_ok

def main():
    print("=== External Service Health Check ===")
    
    # 1. Gemini
    gemini_ok = check_gemini()
    
    # 2. Naver
    naver_ok = check_naver_access()
    
    print("\n=== Check Result ===")
    print(f"Gemini API: {'OK' if gemini_ok else 'FAIL'}")
    print(f"Naver Map : {'OK' if naver_ok else 'FAIL'}")
    
    # 배포 가능 조건: Gemini가 되고, Naver가 되어야 함
    if gemini_ok and naver_ok:
        print("\n✨ Ready to Deploy!")
        sys.exit(0)
    else:
        print("\n🔥 Issues found. Check your environment.")
        sys.exit(1)

if __name__ == "__main__":
    main()

import httpx
import re
import html
import sys
import socket
import os
import json
#import asyncio

sys.stdout.reconfigure(encoding='utf-8')

URL = "https://www.xn--hy1bm6g6ujjkgomr.com/plugin/wz.bookingT1.prm/ajax.calendar.time.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded"
}
COOKIES = {
    'PHPSESSID': 'bnm9bi650n935hea9bipq2dcl7',
    'e1192aefb64683cc97abb83c71057733': 'Ym9va2luZw%3D%3D'
}

#date랑 hour_slots의 hour를 드립합주실 response에 맞게 수정해야함
async def get_dream_availability(business_id, biz_item_id, date, hour_slots):
    try:
        socket.gethostbyname("xn--hy1bm6g6ujjkgomr.com")
        print("[🔧 DNS 프리패칭 완료]")
    except Exception as e:
        print(f"[⚠️ DNS 프리패칭 실패]: {e}")

    data = {
        'rm_ix': biz_item_id,
        'sch_date': date
    }

    async with httpx.AsyncClient() as client:
      response = await client.post(URL, headers=HEADERS, cookies=COOKIES, data=data)
      response_data = response.json()

    available = True
    available_slots = {}
    items_html = html.unescape(response_data.get("items", ""))

    for time in hour_slots:
      target_time = time.split(":")[0] + "시00분"
      pattern = fr'<label[^>]*class=["\']([^"\']*btn-time[^"\']*)["\'][^>]*title=["\'][^"\']*{target_time}[^"\']*["\'][^>]*>'
      match = re.search(pattern, items_html, re.DOTALL)

      if match:
          classes = match.group(1).split()
          available_slots[time] = True if 'active' in classes else False
      else:
          available_slots[time] = False

      if available_slots[time] == False:
         available = False  

    current_dir = os.path.dirname(__file__)  # dream_checker.py의 경로
    room_path = os.path.join(current_dir, '..', 'data', 'rooms.json')

    # JSON 파일 열기
    with open(room_path, 'r', encoding='utf-8') as f:
        rooms = json.load(f)
    
    matches = [ (r["name"], r["branch"]) for r in rooms if r["biz_item_id"] == biz_item_id]
    if matches:
       name, branch = matches[0]
    
    result = {}
    result["name"] = name
    result["branch"] = branch
    result["business_id"] = business_id
    result["available"] = available
    result["available_slots"] = available_slots
    #print(result)

    return result
#테스트 코드
#asyncio.run(get_dream_availability("dream_sadang", "25", "2025-07-08", ["16:00", "17:00"]))
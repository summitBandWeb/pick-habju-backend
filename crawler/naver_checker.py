from playwright.async_api import async_playwright
import re

def convert_korean_time(period: str, hour_text: str) -> str:
    """오전/오후 + 시간 텍스트 ('3시')를 24시간제 HH:00 형식으로 변환"""
    hour = int(re.sub(r"[^\d]", "", hour_text))
    if period == '오전':
        hour = 0 if hour == 12 else hour
    elif period == '오후':
        hour = 12 if hour == 12 else hour + 12
    return f"{hour:02d}:00"

async def fetch_available_times(url: str, room_name: str, date: str, hour_slots: list[str]) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(url)
        await page.wait_for_timeout(2000)

        result = {}
        try:
            await page.wait_for_selector("li.time_item", timeout=10000)
            time_items = await page.query_selector_all("li.time_item")
        except Exception as e:
            print(f"❌ 시간 슬롯 로딩 실패: {e}")
            await browser.close()
            return {}

        last_known_period = None

        for item in time_items:
            class_attr = await item.get_attribute("class")
            is_available = "disabled" not in class_attr

            time_span = await item.query_selector("span.time_text")
            if not time_span:
                continue

            # 오전/오후 처리
            ampm_span = await time_span.query_selector("span.ampm")
            if ampm_span:
                last_known_period = (await ampm_span.inner_text()).strip()

            full_text = (await time_span.inner_text()).replace("\n", "").strip()
            if last_known_period:
                hour_text = full_text.replace(last_known_period, "").strip()
            else:
                hour_text = full_text.strip()

            try:
                converted = convert_korean_time(last_known_period, hour_text)
            except Exception as e:
                print(f"❌ 시간 파싱 오류: '{full_text}' → {e}")
                continue

            print(f"🕒 슬롯: '{full_text}' → {converted} / {'가능' if is_available else '불가능'}")

            if converted in hour_slots:
                result[converted] = is_available

        await browser.close()
        return result
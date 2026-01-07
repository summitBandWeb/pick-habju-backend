from app.crawler.dream_checker import get_dream_availability
from app.crawler.groove_checker import get_groove_availability
from app.crawler.naver_checker import get_naver_availability

CRAWLER_REGISTRY = {
    # "합주실 타입": 크롤러함수
    "dream": get_dream_availability,
    "groove": get_groove_availability,
    "naver": get_naver_availability, 
    # "hapjusil": get_hapjusil_availability,
    # "kakao": get_kakao_availability
}

"""
Rate Limiter 모듈
순환 임포트를 피하기 위해 limiter를 중앙 집중화
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# 사용자의 IP 주소를 기준으로 제한
limiter = Limiter(key_func=get_remote_address)

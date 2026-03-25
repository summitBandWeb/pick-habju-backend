# 수동 검토 플래그 값 — 인원수 파싱 실패 시 할당되는 sentinel 값
# 합주실 최대 수용 인원이 100명을 초과하는 경우는 현실적으로 없으므로
# 이 값이 DB에 저장된 경우 수동 검토 대상으로 식별한다.
# RoomDetail.MANUAL_REVIEW_CAPACITY_FLAG, RoomCollectionService.MANUAL_REVIEW_FLAG 와 동기화
MANUAL_REVIEW_CAPACITY_FLAG: int = 100

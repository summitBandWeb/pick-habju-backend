# Metadata V2 Migration Guide

## 목적
metadata v2 컬럼(`recommend_capacity_range`, `price_config`, `base_capacity`, `extra_charge`)을 안전하게 적용하고 legacy 데이터를 백필하기 위한 운영 가이드임.

## 실행 순서
1. 스키마 변경 SQL 실행
2. legacy 데이터 백필 실행
3. 검증 쿼리 실행
4. 애플리케이션 smoke test 실행

## 실행 스크립트
- 파일: `migrations/155_metadata_v2.sql`
- 특징: `IF NOT EXISTS` 기반으로 재실행 가능(idempotent)

## 검증 기준
- `recommend_capacity`가 있는 row는 `recommend_capacity_range`가 채워져야 함
- `price_per_hour`가 있는 row는 `price_config`가 채워져야 함
- API `/api/rooms/availability`가 기존 케이스에서 정상 동작해야 함

## 롤백 가이드
스키마 롤백은 데이터 손실 위험이 있으므로 권장하지 않음. 운영 문제 발생 시 아래 순서로 대응:
1. 애플리케이션을 이전 버전으로 롤백
2. 신규 컬럼은 유지한 채 읽기 경로만 legacy 필드 우선으로 전환
3. 원인 분석 후 재배포

## 점검 체크리스트
- [ ] 스테이징 환경에서 SQL 재실행 테스트 완료
- [ ] 백필 전/후 row count 비교 완료
- [ ] 주요 API 회귀 테스트 완료
- [ ] 배포 공지/리뷰 완료

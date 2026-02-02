#!/bin/bash

# 가상 환경 생성 (이미 존재하는 경우 다시 만들지 않음)
if [ ! -d "venv" ]; then
  echo "가상 환경을 생성합니다..."
  python3 -m venv venv || { echo "가상 환경 생성 실패."; exit 1; }
fi

# 가상 환경 활성화
echo "가상 환경을 활성화합니다..."
source venv/bin/activate || { echo "가상 환경 활성화 실패."; exit 1; }

# pip 업데이트 (최신 pip를 사용하기 위해)
echo "pip를 업데이트합니다..."
pip install --upgrade pip || { echo "pip 업데이트 실패."; exit 1; }

# requirements.txt 설치
echo "의존성 패키지를 설치합니다..."
pip install -r requirements.txt || { echo "패키지 설치 실패."; exit 1; }

# (이전 프로세스 종료 및 새 프로세스 시작 로직)
echo "이전 프로세스를 종료합니다..."
# 이 부분은 사용자 환경에 맞게 수정
# 예시: Gunicorn/Uvicorn 프로세스를 PID 파일로 종료
PID_FILE="/home/ubuntu/pick-habju-backend/uvicorn.pid"
if [ -f "$PID_FILE" ]; then
    kill $(cat "$PID_FILE") || true
    rm -f "$PID_FILE"
    echo "이전 프로세스 종료됨."
else
    echo "실행 중인 이전 프로세스를 찾을 수 없습니다."
fi

# 애플리케이션 시작 (백그라운드에서)
echo "애플리케이션을 시작합니다..."
# 프로젝트 루트가 /home/ubuntu/pick-habju-backend 이고,
# app/main.py 가 핵심 앱이라면
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 > access.log 2>&1 &
# Uvicorn이 백그라운드에서 실행되도록 nohup과 & 사용

# Uvicorn PID를 파일에 저장 (선택 사항, 프로세스 관리용)
echo $! > "$PID_FILE"
echo "애플리케이션이 백그라운드에서 시작되었습니다. PID: $!"

echo "배포가 성공적으로 완료되었습니다."
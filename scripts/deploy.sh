#!/bin/bash

# 필수 명령어 설치 여부 확인
command -v lsof > /dev/null 2>&1 || { echo "lsof가 설치되어 있지 않습니다. 설치 후 재배포하세요."; exit 1; }

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

# 포트 8000을 사용하는 모든 프로세스 종료
echo "포트 8000을 사용하는 프로세스를 종료합니다..."

# lsof를 사용하여 포트 8000을 점유하는 프로세스 PID 찾기
PIDS=$(lsof -t -i:8000 2>/dev/null) || true

if [ -n "$PIDS" ]; then
    echo "종료할 프로세스 PID: $PIDS"
    
    # 먼저 SIGTERM으로 우아한 종료 시도
    echo "$PIDS" | xargs kill -15 2>/dev/null || true
    sleep 2
    
    # SIGTERM 후 아직 실행 중인 프로세스가 있으면 SIGKILL로 강제 종료
    PIDS=$(lsof -t -i:8000 2>/dev/null) || true
    if [ -n "$PIDS" ]; then
        echo "SIGTERM 후 아직 실행 중인 프로세스를 강제 종료합니다. PID: $PIDS"
        echo "$PIDS" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
    
    echo "이전 프로세스 종료됨."
else
    echo "포트 8000에서 실행 중인 프로세스가 없습니다."
fi

# 추가 안전장치: fuser로 한번 더 확인 및 SIGKILL로 강제 종료
fuser -k -s KILL 8000/tcp 2>/dev/null || true

# 포트 해제 대기 루프 (최대 10초)
for i in $(seq 1 10); do
    if ! lsof -i:8000 > /dev/null 2>&1; then
        echo "포트 8000이 해제되었습니다."
        break
    fi
    echo "포트 8000 해제 대기 중... (${i}s)"
    sleep 1
done

# 애플리케이션 시작 (백그라운드에서)
echo "애플리케이션을 시작합니다..."
# 프로젝트 루트가 /home/ubuntu/pick-habju-backend 이고,
# app/main.py 가 핵심 앱이라면
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 > access.log 2>&1 &
# Uvicorn이 백그라운드에서 실행되도록 nohup과 & 사용

echo "애플리케이션이 백그라운드에서 시작되었습니다. PID: $!"

echo "배포가 성공적으로 완료되었습니다."
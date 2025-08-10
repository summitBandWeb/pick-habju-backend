#!/bin/bash

# 1. 변수 설정
PROJECT_DIR="/home/ubuntu/app"
VENV_PATH="$PROJECT_DIR/venv" # 가상환경 경로
LOG_PATH="/home/ubuntu/deploy.log"
ERR_LOG_PATH="/home/ubuntu/deploy_err.log"

echo ">>> 배포 시작: $(date +%Y-%m-%d_%H:%M:%S)" >> $LOG_PATH

# 2. 현재 실행 중인 Uvicorn 프로세스 PID 찾기
# 'uvicorn'이라는 이름으로 실행된 프로세스를 찾습니다.
CURRENT_PID=$(pgrep -f uvicorn)

# 3. 실행 중이면 종료
if [ -z "$CURRENT_PID" ]; then
  echo ">>> 현재 실행중인 애플리케이션이 없습니다." >> $LOG_PATH
else
  echo ">>> 실행중인 애플리케이션 종료 (PID: $CURRENT_PID)" >> $LOG_PATH
  kill -15 $CURRENT_PID
  sleep 5 # 종료될 때까지 잠시 대기
fi

# 4. 새 애플리케이션 배포
echo ">>> 새 애플리케이션 배포" >> $LOG_PATH

# 가상환경 활성화 및 애플리케이션 실행
# 프로젝트 루트 디렉토리로 이동하여 실행해야 main:app 등을 올바르게 찾습니다.
cd $PROJECT_DIR
python3 -m venv $VENV_PATH
source $VENV_PATH/bin/activate
pip install -r requirements.txt # 배포 시점마다 최신 패키지 설치

nohup uvicorn main:app --host 0.0.0.0 --port 8000 > $LOG_PATH 2> /home/ubuntu/deploy_err.log &
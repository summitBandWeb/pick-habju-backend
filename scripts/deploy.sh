#!/bin/bash

# 이 스크립트는 GitHub Actions 워크플로우에 의해
# 프로젝트의 루트 디렉토리에서 실행됩니다.
# 모든 경로는 현재 디렉토리(./)를 기준으로 합니다.

# 1. 변수 설정
VENV_PATH="./venv" # 현재 디렉토리(프로젝트 루트)에 venv 폴더
PID_FILE="./uvicorn.pid" # 현재 디렉토리(프로젝트 루트)에 PID 파일
# 로그 파일은 프로젝트 폴더 외부에 두는 것이 좋습니다.
LOG_PATH="/home/ubuntu/deploy.log" 
ERR_LOG_PATH="/home/ubuntu/deploy_err.log"

echo ">>> 배포 시작: $(date +%Y-%m-%d_%H:%M:%S)" >> "$LOG_PATH"

# 2. 현재 실행 중인 애플리케이션 종료
if [ -f "$PID_FILE" ]; then
    CURRENT_PID=$(cat "$PID_FILE")
    echo ">>> 실행중인 애플리케이션 종료 (PID: $CURRENT_PID)" >> "$LOG_PATH"
    kill -15 "$CURRENT_PID"
    sleep 5
    # PID 파일 삭제
    # 만약 PID 파일이 없으면 kill 명령어가 실패할 수 있으므로, 종료 후 삭제
    if [ -f "$PID_FILE" ]; then
        rm "$PID_FILE"
    fi
else
    echo ">>> 현재 실행중인 애플리케이션이 없습니다." >> "$LOG_PATH"
fi

# 3. 새 애플리케이션 배포
echo ">>> 새 애플리케이션 배포" >> "$LOG_PATH"

# 가상환경 생성 및 활성화
# venv 폴더가 없다면 새로 생성하고, 있다면 재활용합니다.
python3 -m venv "$VENV_PATH"
source "$VENV_PATH/bin/activate"

# 패키지 설치
# requirements.txt 파일이 현재 디렉토리(프로젝트 루트)에 있습니다.
pip install -r requirements.txt

# Uvicorn 실행 시 --pid-file 옵션을 사용하여 PID 파일을 생성합니다.
# nohup을 사용하여 백그라운드(&)로 실행하고, 로그를 별도 파일로 리디렉션합니다.
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --pid-file "$PID_FILE" >> "$LOG_PATH" 2>> "$ERR_LOG_PATH" &

# 4. Uvicorn이 성공적으로 시작되었는지 확인
# PID 파일이 생성될 때까지 최대 10초간 대기합니다.
for i in {1..10}; do
    if [ -f "$PID_FILE" ]; then
        echo ">>> 애플리케이션이 성공적으로 시작되었습니다." >> "$LOG_PATH"
        exit 0
    fi
    sleep 1
done

echo ">>> 오류: 애플리케이션 시작 실패" >> "$ERR_LOG_PATH"
exit 1
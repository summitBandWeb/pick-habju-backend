#!/bin/bash

# 1. 변수 설정
PROJECT_DIR="/home/ubuntu/app"
VENV_PATH="$PROJECT_DIR/venv"
PID_FILE="$PROJECT_DIR/uvicorn.pid" # 💡 PID 파일 경로를 명시
LOG_PATH="/home/ubuntu/deploy.log"
ERR_LOG_PATH="/home/ubuntu/deploy_err.log"

echo ">>> 배포 시작: $(date +%Y-%m-%d_%H:%M:%S)" >> $LOG_PATH

# 2. 현재 실행 중인 애플리케이션 종료
# PID 파일이 존재하는지 확인
if [ -f "$PID_FILE" ]; then
    CURRENT_PID=$(cat "$PID_FILE")
    echo ">>> 실행중인 애플리케이션 종료 (PID: $CURRENT_PID)" >> $LOG_PATH
    kill -15 "$CURRENT_PID"
    sleep 5 # 종료될 때까지 잠시 대기
else
    echo ">>> 실행중인 애플리케이션이 없습니다." >> $LOG_PATH
fi

# 3. 새 애플리케이션 배포
echo ">>> 새 애플리케이션 배포" >> $LOG_PATH

cd $PROJECT_DIR
python3 -m venv $VENV_PATH
source $VENV_PATH/bin/activate
pip install -r requirements.txt

# 💡 Uvicorn 실행 시 --pid-file 옵션을 사용하여 PID 파일을 생성합니다.
# 💡 로그는 별도 파일로 리디렉션하여 관리하고, 백그라운드(&)로 실행합니다.
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --pid-file "$PID_FILE" > "$LOG_PATH" 2> "$ERR_LOG_PATH" &

# 4. Uvicorn이 성공적으로 시작되었는지 확인
# PID 파일이 생성될 때까지 대기
for i in {1..10}; do
    if [ -f "$PID_FILE" ]; then
        echo ">>> 애플리케이션이 성공적으로 시작되었습니다." >> $LOG_PATH
        exit 0
    fi
    sleep 1
done

echo ">>> 오류: 애플리케이션 시작 실패" >> "$ERR_LOG_PATH"
exit 1
#!/bin/bash

# 跳转到脚本所在目录
cd "$(dirname "$0")" || exit 1

BACKEND_SCRIPT_PATH="reverie/backend_server"
BACKEND_SCRIPT_FILE="automatic_execution.py"
CONDA_ENV="sitanfu"
LOGS_PATH="../../logs"

FILE_NAME="Bash-Script"
cd "${BACKEND_SCRIPT_PATH}" || exit 1
source /home/"${USER}"/anaconda3/bin/activate "${CONDA_ENV}"

ARGS=""
TARGET=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --origin|-o)
            ARGS="${ARGS} --origin ${2}"
            shift 2
            ;;
        --target|-t)
            ARGS="${ARGS} --target ${2}"
            TARGET=${2}
            shift 2
            ;;
        --steps|-s)
            ARGS="${ARGS} --steps ${2}"
            shift 2
            ;;
        --ui)
            ARGS="${ARGS} --ui ${2}"
            shift 2
            ;;
        --browser_path|-bp)
            ARGS="${ARGS} --browser_path ${2}"
            shift 2
            ;;
        --port|-p)
            ARGS="${ARGS} --port ${2}"
            echo "(${FILE_NAME}): Running backend server at: http://127.0.0.1:${2}/simulator_home"
            shift 2
            ;;
        --owner)
            ARGS="${ARGS} --owner ${2}"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

echo "(${FILE_NAME}): Arguments: ${ARGS}"

# 使用 24 小时格式设置时间戳
timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
echo "(${FILE_NAME}): Timestamp: ${timestamp}"
mkdir -p "${LOGS_PATH}"
python3 "${BACKEND_SCRIPT_FILE}" ${ARGS} | tee "${LOGS_PATH}/${TARGET}_${timestamp}.txt"
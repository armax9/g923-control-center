#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 sdk-lab/tools/lab.py collect
printf '\nДиагностика завершена. Отчёт: work/sdk-lab/collection.json в папке этой задачи.\nНикакие эффекты или SDK-функции не запускались.\n'

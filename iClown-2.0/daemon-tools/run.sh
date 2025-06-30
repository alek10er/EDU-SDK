#!/bin/bash

# Убедитесь, что скрипт выполняется от имени root
if [ "$(id -u)" -ne "0" ]; then
  echo "Этот скрипт должен быть запущен от имени root."
  exit 1
fi

# Создание виртуального окружения
python3 -m venv /root/myenv

# Активирование виртуального окружения
source /root/myenv/bin/activate

# Переход в нужную директорию
cd /root/iClown2.0 || { echo "Не удалось перейти в директорию /root/iClown"; exit 1; }

# Запуск Python скрипта
python3 app.py
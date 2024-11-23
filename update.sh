#!/bin/bash
cd /home/botuser/reminderhero
git config --global --add safe.directory /home/botuser/reminderhero
git fetch origin main      # Получаем изменения только из main ветки
git reset --hard origin/main  # Принудительно синхронизируем с main
source .venv/bin/activate
pip install -r requirements.txt
sudo supervisorctl restart tgbot 
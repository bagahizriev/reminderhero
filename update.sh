#!/bin/bash
cd /home/botuser/ваш-репозиторий
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo supervisorctl restart tgbot 
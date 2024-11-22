#!/bin/bash
cd /home/botuser/reminderhero
git config --global --add safe.directory /home/botuser/reminderhero
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo supervisorctl restart tgbot 
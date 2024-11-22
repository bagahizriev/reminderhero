#!/bin/bash
if ! pgrep -f "python bot.py" > /dev/null
then
    sudo supervisorctl restart tgbot
    echo "Bot restarted at $(date)" >> /home/botuser/ваш-репозиторий/restart.log
fi 
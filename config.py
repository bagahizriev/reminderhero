import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
HUGGING_FACE_TOKEN = os.getenv('HUGGING_FACE_TOKEN')
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')
DATABASE_PATH = 'reminders.db'
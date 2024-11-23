import os
from dotenv import load_dotenv

# Базовая директория для файлов экземпляра
INSTANCE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')

# Создаем необходимые директории
os.makedirs(INSTANCE_PATH, exist_ok=True)
os.makedirs(os.path.join(INSTANCE_PATH, 'voice_messages'), exist_ok=True)
os.makedirs(os.path.join(INSTANCE_PATH, 'logs'), exist_ok=True)

# Пути к файлам
DATABASE_PATH = os.path.join(INSTANCE_PATH, 'reminders.db')
ENV_PATH = os.path.join(INSTANCE_PATH, '.env')

# Загружаем переменные окружения
load_dotenv(ENV_PATH)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
HUGGING_FACE_TOKEN = os.getenv('HUGGING_FACE_TOKEN')
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')
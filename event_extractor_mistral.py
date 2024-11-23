import json
from datetime import datetime
import pytz
import requests
from config import MISTRAL_API_KEY
import logging

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/mistral.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('MistralAI')

class EventExtractorMistral:
    def __init__(self):
        self.api_key = MISTRAL_API_KEY
        self.api_url = "https://api.mistral.ai/v1/chat/completions"
        self.model = "mistral-medium-latest"
        logger.info(f"""
{'='*50}
Инициализация EventExtractorMistral:
- Модель: {self.model}
- API URL: {self.api_url}
- Описание: Средняя модель Mistral AI (баланс между скоростью и качеством)
{'='*50}
""")
        
    async def extract_event_data(self, text: str, user_timezone: str = 'UTC') -> dict:
        logger.info(f"\n{'='*50}\nНовый запрос на обработку текста")
        logger.info(f"Входной текст: {text}")
        logger.info(f"Часовой пояс пользователя: {user_timezone}")
        
        # Получаем текущее время в часовом поясе пользователя
        local_tz = pytz.timezone(user_timezone)
        current_time = datetime.now(local_tz)
        logger.info(f"Текущее время пользователя: {current_time}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Формируем промпт для модели
        system_prompt = (
            "Ты - ассистент, который извлекает информацию о событиях из текста. "
            "Всегда отвечай в формате JSON с полями 'description' и 'datetime'. "
            "Поле datetime должно быть в формате 'YYYY-MM-DD HH:MM'. "
            "Описание события должно быть максимально кратким (2-4 слова), отражая только суть. "
            "Всегда используй предоставленное текущее время как точку отсчета для расчетов. "
            "Если указано конкретное время (например, '3 часа дня', '15:00', 'три часа дня'), "
            "используй именно это время, а не 00:00."
        )
        
        user_prompt = (
            f"Текущее время: {current_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"Текущий год: {current_time.year}\n"
            f"Часовой пояс пользователя: {user_timezone}\n"
            f"Текст: {text}\n\n"
            "Правила обработки времени:\n"
            "1. Если указано '3 дня' - это 15:00\n"
            "2. Если указано 'три часа' - это 15:00\n"
            "3. Всегда используй 24-часовой формат\n"
            "4. Никогда не используй 00:00, если время не указано явно\n\n"
            "Примеры обработки времени:\n"
            "- 'завтра в 3 дня' -> завтрашняя дата в 15:00\n"
            "- 'послезавтра в военкомат в 3 дня' -> дата через 2 дня в 15:00\n"
            "- 'встреча в 3 часа' -> сегодня в 15:00\n"
            "- 'в три часа дня' -> сегодня в 15:00\n\n"
            "Правила обработки описания:\n"
            "1. Описание должно быть максимально кратким (2-4 слова)\n"
            "2. Используй существительные и глаголы\n"
            "3. Убирай все лишние детали\n"
            "4. Оставляй только главную суть события\n\n"
            "Примеры описаний:\n"
            "- 'Нужно купить хлеба и молока в магазине' -> 'Купить продукты'\n"
            "- 'Встреча с Иваном Петровичем по поводу проекта' -> 'Встреча по проекту'\n"
            "- 'Не забыть забрать вещи из химчистки на улице Ленина' -> 'Забрать химчистку'\n"
            "- 'Записаться к стоматологу на осмотр' -> 'Визит к стоматологу'\n"
            "- 'Послезавтра в военкомат в 3 дня' -> 'Посещение военкомата'\n\n"
            "Верни строго в формате JSON:\n"
            "{\n"
            '    "description": "краткое описание",\n'
            '    "datetime": "YYYY-MM-DD HH:MM"\n'
            "}"
        )
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 100
        }
        
        logger.info("Отправляем запрос к Mistral AI:")
        logger.info(f"Используемая модель: {self.model}")
        logger.info(f"Температура: {payload['temperature']}")
        logger.info(f"Максимум токенов: {payload['max_tokens']}")
        
        try:
            logger.info("Отправка запроса к API...")
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info("Получен ответ от API:")
            logger.info(f"Полный ответ: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            # Извлекаем JSON из ответа модели
            content = result["choices"][0]["message"]["content"]
            logger.info(f"Извлеченный контент: {content}")
            
            event_data = json.loads(content)
            logger.info(f"Распарсенные данные события: {event_data}")
            
            # Проверяем наличие необходимых полей
            if not all(key in event_data for key in ['description', 'datetime']):
                logger.error("Отсутствуют необходимые поля в ответе")
                raise ValueError("Отсутствуют необходимые поля в ответе")
            
            # Преобразуем дату с учетом часового пояса
            event_dt = datetime.strptime(event_data['datetime'], '%Y-%m-%d %H:%M')
            local_dt = local_tz.localize(event_dt)
            logger.info(f"Локальное время события: {local_dt}")
            
            # Если дата уже прошла в этом году, добавляем год
            if local_dt < current_time:
                next_year = current_time.year + 1
                local_dt = local_dt.replace(year=next_year)
                logger.info(f"Дата в прошлом, перенесено на следующий год: {local_dt}")
            
            # Конвертируем в UTC для хранения
            utc_dt = local_dt.astimezone(pytz.UTC)
            event_data['datetime'] = utc_dt.strftime('%Y-%m-%d %H:%M')
            
            logger.info(f"Итоговые данные события: {event_data}")
            logger.info(f"{'='*50}\n")
            
            return event_data
            
        except Exception as e:
            logger.error(f"Ошибка при обработке: {str(e)}")
            logger.error(f"Исходный текст: {text}")
            logger.exception("Полный стек ошибки:")
            raise ValueError(f"Не удалось распознать дату и время события: {str(e)}") 
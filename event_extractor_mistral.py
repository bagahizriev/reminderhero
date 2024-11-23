import json
from datetime import datetime
import pytz
import requests
from config import MISTRAL_API_KEY

class EventExtractorMistral:
    def __init__(self):
        self.api_key = MISTRAL_API_KEY
        self.api_url = "https://api.mistral.ai/v1/chat/completions"
        self.model = "mistral-small-latest"
        
    async def extract_event_data(self, text: str, user_timezone: str = 'UTC') -> dict:
        # Получаем текущее время в часовом поясе пользователя
        local_tz = pytz.timezone(user_timezone)
        current_time = datetime.now(local_tz)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты - ассистент, который извлекает информацию о событиях из текста. "
                        "Всегда отвечай в формате JSON с полями 'description' и 'datetime'. "
                        "Поле datetime должно быть в формате 'YYYY-MM-DD HH:MM'. "
                        "Описание события должно быть максимально кратким (2-4 слова), отражая только суть. "
                        "Всегда используй предоставленное текущее время как точку отсчета для расчетов."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Текущее время: {current_time.strftime('%Y-%m-%d %H:%M')}\n"
                        f"Текущий год: {current_time.year}\n"
                        f"Часовой пояс пользователя: {user_timezone}\n"
                        f"Текст: {text}\n\n"
                        "Правила обработки описания:\n"
                        "1. Описание должно быть максимально кратким (2-4 слова)\n"
                        "2. Используй существительные и глаголы\n"
                        "3. Убирай все лишние детали\n"
                        "4. Оставляй только главную суть события\n\n"
                        "Примеры описаний:\n"
                        "- 'Нужно купить хлеба и молока в магазине' -> 'Купить продукты'\n"
                        "- 'Встреча с Иваном Петровичем по поводу проекта' -> 'Встреча по проекту'\n"
                        "- 'Не забыть забрать вещи из химчистки на улице Ленина' -> 'Забрать химчистку'\n"
                        "- 'Записаться к стоматологу на осмотр' -> 'Визит к стоматологу'\n\n"
                        "Верни строго в формате JSON:\n"
                        "{\n"
                        '    "description": "краткое описание",\n'
                        '    "datetime": "YYYY-MM-DD HH:MM"\n'
                        "}"
                    )
                }
            ],
            "temperature": 0.1,
            "max_tokens": 100
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            # Извлекаем JSON из ответа модели
            content = result["choices"][0]["message"]["content"]
            event_data = json.loads(content)
            
            # Проверяем наличие необходимых полей
            if not all(key in event_data for key in ['description', 'datetime']):
                raise ValueError("Отсутствуют необходимые поля в ответе")
            
            # Преобразуем дату с учетом часового пояса
            event_dt = datetime.strptime(event_data['datetime'], '%Y-%m-%d %H:%M')
            local_dt = local_tz.localize(event_dt)
            
            # Если дата уже прошла в этом году, добавляем год
            if local_dt < current_time:
                next_year = current_time.year + 1
                local_dt = local_dt.replace(year=next_year)
            
            # Конвертируем в UTC для хранения
            utc_dt = local_dt.astimezone(pytz.UTC)
            event_data['datetime'] = utc_dt.strftime('%Y-%m-%d %H:%M')
            
            return event_data
            
        except Exception as e:
            print(f"Ошибка при обработке: {str(e)}")
            print(f"Исходный текст: {text}")
            raise ValueError(f"Не удалось распознать дату и время события: {str(e)}") 
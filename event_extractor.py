import json
from datetime import datetime
import pytz
from huggingface_hub import InferenceClient
from config import HUGGING_FACE_TOKEN

class EventExtractor:
    def __init__(self):
        self.client = InferenceClient(api_key=HUGGING_FACE_TOKEN)
        self.model = "microsoft/Phi-3-mini-4k-instruct"
    
    async def extract_event_data(self, text: str, user_timezone: str = 'UTC') -> dict:
        # Получаем текущее время в часовом поясе пользователя
        local_tz = pytz.timezone(user_timezone)
        current_time = datetime.now(local_tz)
        
        messages = [
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
                    "Правила обработки времени:\n"
                    "1. Если в тексте есть 'через X минут' - добавь X минут к текущему времени\n"
                    "2. Если в тексте есть 'через X часов' или 'через X часа' - добавь X часов к текущему времени\n"
                    "3. Если в тексте есть 'через X дней' или 'через X дня' - добавь X дней к текущей дате\n"
                    "4. Если в тексте указана конкретная дата без года:\n"
                    "   - Если дата уже прошла в этом году, используй следующий год\n"
                    "   - Если дата ещё не наступила, используй текущий год\n"
                    "5. Если в тексте есть 'завтра' - используй следующий день\n"
                    "6. Если в тексте есть 'послезавтра' - используй день после завтра\n"
                    "7. Если указано только время - используй ближайшую возможную дату\n"
                    "8. Если в тексте есть 'в X часов' или 'в X:XX' - используй указанное время\n"
                    "9. Если в тексте есть 'утром' без точного времени - используй 09:00\n"
                    "10. Если в тексте есть 'днём' или 'днем' без точного времени - используй 13:00\n"
                    "11. Если в тексте есть 'вечером' без точного времени - используй 19:00\n"
                    "12. Если в тексте есть 'ночью' без точного времени - используй 23:00\n\n"
                    "ВАЖНО: Используй предоставленное текущее время как базу для всех расчётов!\n\n"
                    "Примеры:\n"
                    f"- Текущее время {current_time.strftime('%H:%M')}, текст 'через 2 минуты' -> добавить 2 минуты к {current_time.strftime('%H:%M')}\n"
                    f"- Текущее время {current_time.strftime('%H:%M')}, текст 'через час' -> добавить 1 час к {current_time.strftime('%H:%M')}\n"
                    f"- Текущее время {current_time.strftime('%H:%M')}, текст 'завтра утром' -> следующий день в 09:00\n"
                    f"- Текущее время {current_time.strftime('%H:%M')}, текст '25 марта вечером' -> 25 марта в 19:00\n"
                    f"- Текущее время {current_time.strftime('%H:%M')}, текст 'в 15:30' -> сегодня в 15:30 (или завтра, если время уже прошло)\n"
                    "Верни строго в формате JSON:\n"
                    "{\n"
                    '    "description": "краткое описание",\n'
                    '    "datetime": "YYYY-MM-DD HH:MM"\n'
                    "}"
                )
            }
        ]
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=500,
                temperature=0.1
            )
            
            response = completion.choices[0].message.content
            print(f"Ответ от модели: {response}")
            
            # Очищаем ответ от возможного лишнего текста
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:]
            if response.endswith('```'):
                response = response[:-3]
            response = response.strip()
            
            # Находим JSON в тексте
            start = response.find('{')
            end = response.rfind('}') + 1
            if start == -1 or end == 0:
                raise ValueError("JSON не найден в ответе")
            
            json_str = response[start:end]
            event_data = json.loads(json_str)
            
            if not all(key in event_data for key in ['description', 'datetime']):
                raise ValueError("Отсутствуют необходимые поля в ответе")
            
            # Преобразуем дату с учетом часового пояса
            event_dt = datetime.strptime(event_data['datetime'], '%Y-%m-%d %H:%M')
            # Важно: считаем, что время от модели уже в часовом поясе пользователя
            local_dt = local_tz.localize(event_dt)
            
            # Если дата уже прошла в этом году, добавляем год
            if local_dt < current_time:
                next_year = current_time.year + 1
                local_dt = local_dt.replace(year=next_year)
                print(f"Дата {event_dt.strftime('%d.%m.%Y')} уже прошла, используем следующий год: {next_year}")
            
            # Конвертируем в UTC для хранения
            utc_dt = local_dt.astimezone(pytz.UTC)
            event_data['datetime'] = utc_dt.strftime('%Y-%m-%d %H:%M')
            
            return event_data
            
        except Exception as e:
            print(f"Ошибка при обработке: {str(e)}")
            print(f"Исходный текст: {text}")
            raise ValueError(f"Не удалось распознать дату и время события: {str(e)}")
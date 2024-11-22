import os
import ffmpeg
import requests
import time
from config import HUGGING_FACE_TOKEN

class SpeechRecognizer:
    def __init__(self):
        self.API_URL = "https://api-inference.huggingface.co/models/openai/whisper-large-v3-turbo"
        self.headers = {"Authorization": f"Bearer {HUGGING_FACE_TOKEN}"}
        self.max_retries = 3
        self.retry_delay = 2  # секунды

    def convert_ogg_to_wav(self, input_path: str, output_path: str):
        """Конвертирует .ogg файл в .wav"""
        try:
            stream = ffmpeg.input(input_path)
            stream = ffmpeg.output(stream, output_path)
            ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            print('stdout:', e.stdout.decode('utf8'))
            print('stderr:', e.stderr.decode('utf8'))
            raise

    def transcribe(self, audio_path: str) -> str:
        """Отправляет аудиофайл на распознавание в Hugging Face"""
        with open(audio_path, "rb") as f:
            data = f.read()
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.API_URL,
                    headers=self.headers,
                    data=data,
                    timeout=30
                )
                
                # Проверяем специфичные ошибки Hugging Face
                if response.status_code == 503:
                    if attempt < self.max_retries - 1:
                        print(f"Сервис временно недоступен. Попытка {attempt + 1} из {self.max_retries}")
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        raise Exception("Сервис Hugging Face временно недоступен. Пожалуйста, попробуйте позже.")
                
                response.raise_for_status()
                result = response.json()
                print(f"Ответ от модели распознавания речи: {result}")
                
                # Новый формат ответа для whisper-large-v3-turbo
                if isinstance(result, dict):
                    if "error" in result:
                        raise Exception(f"Ошибка API: {result['error']}")
                    elif "text" in result:
                        return result["text"].strip()
                    elif "translation" in result:  # Иногда модель возвращает перевод
                        return result["translation"]["text"].strip()
                    
                raise ValueError(f"Неожиданный формат ответа: {result}")
                
            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    print(f"Таймаут запроса. Попытка {attempt + 1} из {self.max_retries}")
                    time.sleep(self.retry_delay)
                    continue
                raise Exception("Превышено время ожидания ответа от сервера. Пожалуйста, попробуйте позже.")
                
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    print(f"Ошибка запроса: {str(e)}. Попытка {attempt + 1} из {self.max_retries}")
                    time.sleep(self.retry_delay)
                    continue
                raise Exception(f"Ошибка при распознавании речи: {str(e)}")
                
            except Exception as e:
                print(f"Неожиданная ошибка: {str(e)}")
                raise
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from aiogram import Bot
import pytz
import asyncio
import sqlite3

class NotificationManager:
    def __init__(self, token: str, database):
        self.bot = Bot(token=token)
        self.db = database
        self.scheduler = None  # Инициализируем планировщик позже
    
    async def init_scheduler(self):
        """Инициализация планировщика"""
        if self.scheduler is None:
            jobstores = {
                'default': MemoryJobStore()
            }
            
            self.scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                timezone=pytz.UTC
            )
            
            # Увеличиваем интервал до 60 секунд
            self.scheduler.add_job(
                self.check_notifications,
                'interval',
                seconds=60,  # Было 30, стало 60
                id='check_notifications',
                replace_existing=True,
                next_run_time=datetime.now(pytz.UTC),
                misfire_grace_time=30  # Добавляем допустимое время опоздания
            )
            
            self.scheduler.start()
    
    def schedule_notifications(self, user_id: int, event: dict, user_timezone: str = 'UTC', reminder_id: int = None):
        try:
            event_time = datetime.strptime(event["datetime"], "%Y-%m-%d %H:%M")
            event_time = pytz.UTC.localize(event_time)
            current_time = datetime.now(pytz.UTC)
            
            # Добавляем основное напоминание в список времен
            notify_times = [
                (event_time, "MAIN_EVENT", "прямо сейчас", True),  # Основное напоминание
                (event_time - timedelta(days=3), "REMINDER", "за 3 дня", False),
                (event_time - timedelta(days=2), "REMINDER", "за 2 дня", False),
                (event_time - timedelta(days=1), "REMINDER", "за сутки", False),
                (event_time - timedelta(hours=2), "REMINDER", "за 2 часа", False)
            ]
            
            # Фильтруем будущие напоминания и уведомления
            future_notifications = [
                (notify_time, notif_type, description, is_main) 
                for notify_time, notif_type, description, is_main in notify_times 
                if notify_time > current_time
            ]
            
            if not future_notifications:
                print("Нет будущих уведомлений для планирования")
                return
            
            # Используем существующий reminder_id или создаем новый
            if reminder_id is None:
                reminder_id = self.db.save_reminder(
                    user_id,
                    event["description"],
                    event["datetime"]
                )
            
            # Сохраняем все уведомления и напоминания
            for notify_time, notif_type, description, is_main in future_notifications:
                self.db.save_notification(
                    reminder_id,
                    user_id,
                    notify_time.strftime("%Y-%m-%d %H:%M"),
                    event["description"],
                    description,
                    is_main,
                    notif_type
                )
                print(f"Запланировано {notif_type} на {notify_time}")
                print(f"Для пользователя {user_id}, reminder_id {reminder_id}")
            
        except Exception as e:
            print(f"Ошибка при планировании уведомлений: {str(e)}")
            raise
    
    async def check_notifications(self):
        try:
            current_time = datetime.now(pytz.UTC)
            print(f"\n{'='*50}")
            print(f"Проверка уведомлений в {current_time}")
            
            # Отладочный вывод всех уведомлений
            self.db.debug_notifications()
            
            # Проверяем подключение к базе данных
            try:
                notifications = self.db.get_pending_notifications()
                print("✅ Успешное подключение к БД")
            except Exception as db_error:
                print(f"❌ Ошибка при получении уведомлений из БД: {str(db_error)}")
                return

            if notifications:
                print(f"📬 Найдено {len(notifications)} уведомлений для отправки")
                
                for notification in notifications:
                    (notification_id, user_id, description, event_datetime, 
                     notify_datetime, timing, user_timezone) = notification
                    
                    print(f"\n📌 Обработка уведомления {notification_id}:")
                    print(f"👤 ID пользователя: {user_id}")
                    print(f"📝 Описание: {description}")
                    print(f"📅 Время события: {event_datetime}")
                    print(f"⏰ Время уведомления: {notify_datetime}")
                    print(f"ℹ️ Тип уведомления: {timing}")
                    print(f"🌍 Часовой пояс: {user_timezone}")
                    
                    try:
                        print("✉️ Отправка уведомления...")
                        await self.send_notification(
                            user_id,
                            {"description": description, "datetime": event_datetime},
                            user_timezone or 'UTC',
                            timing
                        )
                        
                        # Получаем reminder_id для этого уведомления
                        with sqlite3.connect(self.db.db_path) as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                SELECT reminder_id FROM notifications
                                WHERE id = ?
                            """, (notification_id,))
                            result = cursor.fetchone()
                            if result:
                                reminder_id = result[0]
                                
                                if timing == "прямо сейчас":
                                    # Если это основное напоминание, удаляем всё
                                    self.db.delete_reminder_with_notifications(reminder_id)
                                    print(f"✅ Напоминание {reminder_id} удалено вместе со всеми уведомлениями")
                                else:
                                    # Для обычного уведомления удаляем только его
                                    cursor.execute("""
                                        DELETE FROM notifications 
                                        WHERE id = ?
                                    """, (notification_id,))
                                    conn.commit()
                                    print(f"✅ Уведомление {notification_id} удалено")
                        
                        print("✅ Уведомление успешно обработано")
                        
                    except Exception as send_error:
                        print(f"❌ Ошибка при отправке уведомления: {str(send_error)}")
            else:
                print("📭 Нет уведомлений для отправки")
            
            print(f"{'='*50}\n")
                    
        except Exception as e:
            print(f"❌ Критическая ошибка при проверке уведомлений: {str(e)}")
    
    async def send_notification(self, user_id: int, event: dict, user_timezone: str, timing: str):
        try:
            event_time = datetime.strptime(event["datetime"], "%Y-%m-%d %H:%M")
            event_time = pytz.UTC.localize(event_time)
            local_tz = pytz.timezone(user_timezone)
            local_time = event_time.astimezone(local_tz)
            
            formatted_date = local_time.strftime("%d.%m.%Y")
            formatted_time = local_time.strftime("%H:%M")
            
            if timing == "прямо сейчас":
                message = (
                    f"Внимание! Событие *{event['description']}* началось! "
                    f"Точная дата и время: *{formatted_date}* *{formatted_time}*."
                )
            elif "часа" in timing:
                hours = "2"
                message = (
                    f"Внимание! Событие *{event['description']}* запланировано через "
                    f"*{hours}* часа, а именно *{formatted_date}* *{formatted_time}*."
                )
            elif any(word in timing for word in ["дня", "сутки"]):
                if "сутки" in timing:
                    days = "1"
                else:
                    days = timing.split()[1]
                    
                message = (
                    f"Внимание! Событие *{event['description']}* запланировано через "
                    f"*{days}* {'день' if days == '1' else 'дня' if days in ['2', '3'] else 'дней'}, "
                    f"а именно *{formatted_date}* *{formatted_time}*."
                )
            
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            print(f"Ошибка при отправке уведомления: {str(e)}")
            raise
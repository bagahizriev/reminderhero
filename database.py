import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self._create_tables()
    
    def _create_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    event_datetime TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    timezone TEXT NOT NULL DEFAULT 'UTC'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY,
                    reminder_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    notify_datetime TEXT NOT NULL,
                    description TEXT NOT NULL,
                    timing_description TEXT NOT NULL,
                    is_sent BOOLEAN DEFAULT 0,
                    is_main BOOLEAN DEFAULT 0,
                    notification_type TEXT NOT NULL,
                    FOREIGN KEY (reminder_id) REFERENCES reminders (id)
                )
            """)
            conn.commit()
    
    def save_reminder(self, user_id: int, description: str, event_datetime: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Всегда создаем новое напоминание без проверки на дубликаты
            cursor.execute("""
                INSERT INTO reminders (user_id, description, event_datetime)
                VALUES (?, ?, ?)
            """, (user_id, description, event_datetime))
            conn.commit()
            return cursor.lastrowid
    
    def save_notification(self, reminder_id: int, user_id: int, notify_datetime: str, 
                         description: str, timing_description: str, is_main: bool = False,
                         notification_type: str = "REMINDER"):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Всегда создаем новое уведомление без проверки на дубликаты
            cursor.execute("""
                INSERT INTO notifications 
                (reminder_id, user_id, notify_datetime, description, timing_description, is_main, notification_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (reminder_id, user_id, notify_datetime, description, timing_description, is_main, notification_type))
            conn.commit()
    
    def get_pending_notifications(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    n.id,
                    n.user_id,
                    r.description,
                    r.event_datetime,
                    n.notify_datetime,
                    n.timing_description,
                    us.timezone
                FROM notifications n
                JOIN reminders r ON n.reminder_id = r.id
                LEFT JOIN user_settings us ON n.user_id = us.user_id
                WHERE n.is_sent = 0 
                AND datetime(n.notify_datetime) <= datetime('now', '+1 minute')
                AND datetime(n.notify_datetime) >= datetime('now', '-1 minute')
                ORDER BY n.notify_datetime
            """
            print(f"\nВыполняется SQL-запрос:\n{query}")
            
            cursor.execute(query)
            results = cursor.fetchall()
            print(f"Найдено записей: {len(results)}")
            
            for row in results:
                print(f"""
                ID: {row[0]}
                User ID: {row[1]}
                Description: {row[2]}
                Event DateTime: {row[3]}
                Notify DateTime: {row[4]}
                Timing: {row[5]}
                Timezone: {row[6]}
                """)
            
            return results
    
    def mark_notification_sent(self, notification_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE notifications 
                SET is_sent = 1 
                WHERE id = ?
            """, (notification_id,))
            conn.commit()
    
    def get_user_reminders(self, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Получаем напоминания с их уведомлениями в одном запросе
            cursor.execute("""
                SELECT 
                    r.id,
                    r.description,
                    r.event_datetime,
                    r.created_at,
                    n.notify_datetime,
                    n.timing_description,
                    n.notification_type,
                    n.is_main
                FROM reminders r
                LEFT JOIN notifications n ON r.id = n.reminder_id
                WHERE r.user_id = ?
                ORDER BY r.event_datetime, r.created_at
            """, (user_id,))
            
            results = cursor.fetchall()
            
            # Группируем результаты по reminder_id
            grouped_reminders = {}
            real_to_display_id = {}  # Словарь для соответствия реальных и отображаемых ID
            display_id = 1  # Начинаем с 1
            
            for row in results:
                reminder_id = row[0]
                
                # Если это новое напоминание, создаем для него запись и сохраняем соответствие ID
                if reminder_id not in grouped_reminders:
                    real_to_display_id[reminder_id] = display_id
                    grouped_reminders[reminder_id] = {
                        'id': reminder_id,  # Реальный ID
                        'display_id': display_id,  # Отображаемый ID
                        'description': row[1],
                        'event_datetime': row[2],
                        'created_at': row[3],
                        'notifications': []
                    }
                    display_id += 1
                
                # Добавляем уведомление, если оно есть и это не основное уведомление
                if row[4] is not None and not row[7]:  # row[7] это is_main
                    grouped_reminders[reminder_id]['notifications'].append({
                        'datetime': row[4],
                        'timing': row[5]
                    })
            
            # Сохраняем соответствие ID в базе данных для последующего использования
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS id_mapping (
                    user_id INTEGER NOT NULL,
                    real_id INTEGER NOT NULL,
                    display_id INTEGER NOT NULL,
                    PRIMARY KEY (user_id, display_id)
                )
            """)
            
            # Очищаем старые маппинги для этого пользователя
            cursor.execute("DELETE FROM id_mapping WHERE user_id = ?", (user_id,))
            
            # Сохраняем новые маппинги
            for real_id, disp_id in real_to_display_id.items():
                cursor.execute("""
                    INSERT INTO id_mapping (user_id, real_id, display_id)
                    VALUES (?, ?, ?)
                """, (user_id, real_id, disp_id))
            
            conn.commit()
            return grouped_reminders
    
    def get_real_reminder_id(self, user_id: int, display_id: int) -> int:
        """Получает реальный ID напоминания по отображаемому ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT real_id FROM id_mapping
                WHERE user_id = ? AND display_id = ?
            """, (user_id, display_id))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def get_user_timezone(self, user_id: int) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timezone FROM user_settings WHERE user_id = ?
            """, (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 'Etc/GMT+0'
    
    def set_user_timezone(self, user_id: int, timezone: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_settings (user_id, timezone)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET timezone = ?
            """, (user_id, timezone, timezone))
            conn.commit()
    
    def delete_reminder(self, reminder_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Сначала удаляем все связанные уведомления
            cursor.execute("""
                DELETE FROM notifications 
                WHERE reminder_id = ?
            """, (reminder_id,))
            
            # Затем удаляем само напоминание
            cursor.execute("""
                DELETE FROM reminders 
                WHERE id = ?
            """, (reminder_id,))
            
            conn.commit()
    
    def debug_notifications(self):
        """Метод для отладки - показывает все уведомления"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    n.id,
                    n.user_id,
                    r.description,
                    r.event_datetime,
                    n.notify_datetime,
                    n.timing_description,
                    n.is_sent
                FROM notifications n
                JOIN reminders r ON n.reminder_id = r.id
                ORDER BY n.notify_datetime
            """)
            results = cursor.fetchall()
            print("\n=== Все уведомления в базе данных ===")
            for row in results:
                print(f"""
                ID: {row[0]}
                User ID: {row[1]}
                Description: {row[2]}
                Event DateTime: {row[3]}
                Notify DateTime: {row[4]}
                Timing: {row[5]}
                Is Sent: {row[6]}
                """)
            return results
    
    def delete_reminder_with_notifications(self, reminder_id: int):
        """Удаляет напоминание и все его уведомления"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                # Получаем ID всех уведомлений для этого напоминания
                cursor.execute("""
                    SELECT id FROM notifications 
                    WHERE reminder_id = ?
                """, (reminder_id,))
                notification_ids = [row[0] for row in cursor.fetchall()]
                
                # Удаляем все уведомления
                cursor.execute("""
                    DELETE FROM notifications 
                    WHERE reminder_id = ?
                """, (reminder_id,))
                
                # Удаляем само напоминание
                cursor.execute("""
                    DELETE FROM reminders 
                    WHERE id = ?
                """, (reminder_id,))
                
                conn.commit()
                print(f"✅ Удалено напоминание {reminder_id} и {len(notification_ids)} связанных уведомлений")
                
            except Exception as e:
                print(f"❌ Ошибка при удалении напоминания: {str(e)}")
                conn.rollback()
                raise
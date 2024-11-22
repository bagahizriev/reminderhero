import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from config import TELEGRAM_TOKEN
from database import Database
from speech_recognition import SpeechRecognizer
from event_extractor import EventExtractor
from notification_manager import NotificationManager
import pytz
from datetime import datetime
from aiogram.filters import StateFilter

class TimezoneStates(StatesGroup):
    waiting_for_timezone = State()

class ManualReminderStates(StatesGroup):
    waiting_for_description = State()
    waiting_for_datetime = State()

class ReminderBot:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_TOKEN)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.db = Database('reminders.db')
        self.speech_recognizer = SpeechRecognizer()
        self.event_extractor = EventExtractor()
        self.notification_manager = NotificationManager(TELEGRAM_TOKEN, self.db)
        self.register_handlers()

    def register_handlers(self):
        # Бзовые команды
        self.dp.message.register(self.start_command, Command("start"))
        self.dp.message.register(self.list_command, Command("list"))
        self.dp.message.register(self.settings_command, Command("settings"))
        
        # Обработка голосовых сообщений
        self.dp.message.register(self.handle_voice, F.voice)
        
        # Обработка установки часового пояса
        self.dp.message.register(
            self.process_timezone_setting,
            TimezoneStates.waiting_for_timezone
        )
        
        # Обработка кнопок
        self.dp.callback_query.register(
            self.cancel_reminder,
            F.data.startswith("cancel_")
        )
        
        # Обработка текстовых сообщений должна быть в конце,
        # после более специфичных обработчиков
        
        # Добавляем обработчики для ручного создания напоминания
        self.dp.message.register(
            self.manual_command, 
            Command("manual")
        )
        
        # Изменяем регистрацию обработчиков состояний
        self.dp.message.register(
            self.process_manual_description,
            F.text,  # Добавляем фильтр на текстовые сообщения
            StateFilter(ManualReminderStates.waiting_for_description)
        )
        self.dp.message.register(
            self.process_manual_datetime,
            F.text,  # Добавляем фильтр на текстовые сообщения
            StateFilter(ManualReminderStates.waiting_for_datetime)
        )
        
        # Обработчик для отмены мануального создания
        self.dp.callback_query.register(
            self.cancel_manual_callback,
            F.data == "cancel_manual"
        )
        
        # Общий обработчик текста должен быть последним
        self.dp.message.register(
            self.handle_text,
            lambda message: not message.voice 
            and not message.text.startswith('/')
            and message.text
        )
        
        # Добавляем обработчики для удаления напоминаний
        self.dp.callback_query.register(
            self.show_delete_buttons,
            F.data == "show_delete_buttons"
        )
        self.dp.callback_query.register(
            self.delete_reminder_by_id,
            F.data.startswith("delete_")
        )
        self.dp.callback_query.register(
            self.save_deletions,
            F.data == "save_deletions"
        )
        
        # Добавляем обработчик для кнопки смены часового пояса
        self.dp.callback_query.register(
            self.show_timezone_change,
            F.data == "change_timezone"
        )
        self.dp.callback_query.register(
            self.save_timezone,
            F.data == "save_timezone"
        )
        
        # Добавляем обработчик для кнопок с часовыми поясами
        self.dp.callback_query.register(
            self.process_timezone_button,
            F.data.startswith("timezone_")
        )

    def format_datetime(self, dt_str: str, user_timezone: str) -> str:
        dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
        dt = pytz.UTC.localize(dt)
        local_dt = dt.astimezone(pytz.timezone(user_timezone))
        return local_dt.strftime('%d.%m.%Y %H:%M')

    async def start_command(self, message: types.Message):
        text = (
            "👋 Привет! Я бот для создания напоминаниййй.\n\n"
            "📝 Команды:\n"
            "/list - показать все напоминания\n"
            "/settings - настроить часовой пояс\n\n"
            "🎤 Отправь мне голосовое сообщение или напиши текстом описание события и дату, "
            "например:\n"
            "- 'Встреча с врачом 25 марта в 14:30'\n"
            "- 'Через 2 часа позвонить маме'\n"
            "- 'Завтра в 15:00 встреча'\n"
            "- 'Через 3 дня забрать документы'"
        )
        await message.answer(text)

    async def list_command(self, message: types.Message):
        user_id = message.from_user.id
        reminders = self.db.get_user_reminders(user_id)
        
        if not reminders:
            await message.answer("У вас пока нет напоминаний.")
            return
        
        user_timezone = self.db.get_user_timezone(user_id)
        text = "📋 Ваши напоминания:\n\n"
        
        for unique_key, reminder_data in reminders.items():
            formatted_datetime = self.format_datetime(
                reminder_data['event_datetime'], 
                user_timezone
            )
            text += f"🎯 Основное событие (ID: {reminder_data['display_id']}):\n"
            text += f"└ {reminder_data['description']}\n"
            text += f"└ {formatted_datetime}\n"
            
            if reminder_data['notifications']:
                text += "├ Дополнительные уведомления:\n"
                for notif in reminder_data['notifications']:
                    formatted_notif_time = self.format_datetime(
                        notif['datetime'],
                        user_timezone
                    )
                    text += f"  └ {notif['timing']} ({formatted_notif_time})\n"
            text += "\n"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="🗑 Удалить по ID",
                callback_data="show_delete_buttons"
            )]
        ])
        
        await message.answer(text, reply_markup=keyboard)

    async def show_delete_buttons(self, callback: types.CallbackQuery):
        user_id = callback.from_user.id
        reminders = self.db.get_user_reminders(user_id)
        
        if not reminders:
            await callback.answer("Нет напоминаний для удаления")
            return
        
        # Создаем текст списка напоминаний
        user_timezone = self.db.get_user_timezone(user_id)
        text = "📋 Ваши напоминания:\n\n"
        
        # Создаем кноп��и для каждого ID напоминания
        buttons = []
        for unique_key, reminder_data in reminders.items():
            formatted_datetime = self.format_datetime(
                reminder_data['event_datetime'], 
                user_timezone
            )
            text += f"🎯 Основное событие (ID: {reminder_data['display_id']}):\n"
            text += f"└ {reminder_data['description']}\n"
            text += f"└ {formatted_datetime}\n"
            
            if reminder_data['notifications']:
                text += "├ Дополнительные уведомления:\n"
                for notif in reminder_data['notifications']:
                    formatted_notif_time = self.format_datetime(
                        notif['datetime'],
                        user_timezone
                    )
                    text += f"  └ {notif['timing']} ({formatted_notif_time})\n"
            text += "\n"
            
            buttons.append([types.InlineKeyboardButton(
                text=f"🗑 ID: {reminder_data['display_id']}",
                callback_data=f"delete_{reminder_data['display_id']}"
            )])
        
        # Добавляем кнопку "Сохранить" внизу
        buttons.append([types.InlineKeyboardButton(
            text="✅ Сохранить",
            callback_data="save_deletions"
        )])
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    async def delete_reminder_by_id(self, callback: types.CallbackQuery):
        display_id = int(callback.data.split('_')[1])
        user_id = callback.from_user.id
        
        try:
            # Получаем реальный ID напоминания
            real_id = self.db.get_real_reminder_id(user_id, display_id)
            if real_id is None:
                await callback.answer("Напоминание не найдено")
                return
            
            # Удаляем напоминание по реальному ID
            self.db.delete_reminder(real_id)
            
            # Обновляем список напоминаний
            reminders = self.db.get_user_reminders(user_id)
            
            if not reminders:
                await callback.message.edit_text("У вас больше нет напоминаний.")
                await callback_query.answer("Напоминание удалено")
                return
            
            # Обновляем текст и кнопки с новыми display_id
            user_timezone = self.db.get_user_timezone(user_id)
            text = "📋 Ваши напоминания:\n\n"
            
            buttons = []
            for unique_key, reminder_data in reminders.items():
                formatted_datetime = self.format_datetime(
                    reminder_data['event_datetime'], 
                    user_timezone
                )
                text += f"🎯 Основное событие (ID: {reminder_data['display_id']}):\n"
                text += f"└ {reminder_data['description']}\n"
                text += f"└ {formatted_datetime}\n"
                
                if reminder_data['notifications']:
                    text += "├ Дополнительные уведомления:\n"
                    for notif in reminder_data['notifications']:
                        formatted_notif_time = self.format_datetime(
                            notif['datetime'],
                            user_timezone
                        )
                        text += f"  └ {notif['timing']} ({formatted_notif_time})\n"
                text += "\n"
                
                buttons.append([types.InlineKeyboardButton(
                    text=f"🗑 ID: {reminder_data['display_id']}",
                    callback_data=f"delete_{reminder_data['display_id']}"
                )])
            
            buttons.append([types.InlineKeyboardButton(
                text="✅ Сохранить",
                callback_data="save_deletions"
            )])
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer("Напоминание удалено")
            
        except Exception as e:
            await callback.answer(f"Ошибка при удалении: {str(e)}")

    async def save_deletions(self, callback: types.CallbackQuery):
        user_id = callback.from_user.id
        reminders = self.db.get_user_reminders(user_id)
        
        if not reminders:
            await callback.message.edit_text("У вас нет напоминаний.")
            await callback.answer()
            return
        
        # Создаем обычный писок с одной кнопкой "Удалить по ID"
        user_timezone = self.db.get_user_timezone(user_id)
        text = "📋 Ваши напоминания:\n\n"
        
        for unique_key, reminder_data in reminders.items():
            formatted_datetime = self.format_datetime(
                reminder_data['event_datetime'], 
                user_timezone
            )
            text += f"🎯 Основное событие (ID: {reminder_data['display_id']}):\n"
            text += f"└ {reminder_data['description']}\n"
            text += f"└ {formatted_datetime}\n"
            
            if reminder_data['notifications']:
                text += "Дополнительные уведомления:\n"
                for notif in reminder_data['notifications']:
                    formatted_notif_time = self.format_datetime(
                        notif['datetime'],
                        user_timezone
                    )
                    text += f"  └ {notif['timing']} ({formatted_notif_time})\n"
            text += "\n"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="🗑 Удалить по ID",
                callback_data="show_delete_buttons"
            )]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer("Изменения сохранены")

    async def settings_command(self, message: types.Message):
        user_timezone = self.db.get_user_timezone(message.from_user.id)
        # Конвертируем Etc/GMT+3 в GMT-3
        display_timezone = user_timezone.replace('Etc/', '')
        if display_timezone.startswith('GMT+'):
            display_timezone = 'GMT' + display_timezone[4:].replace('+', '-')
        elif display_timezone.startswith('GMT-'):
            display_timezone = 'GMT' + display_timezone[4:].replace('-', '+')
        
        text = f"⚙️ Настройки\n\n🌍 Часовой пояс: {display_timezone}"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="🔄 Сменить часовой пояс",
                callback_data="change_timezone"
            )]
        ])
        
        await message.answer(text, reply_markup=keyboard)

    async def show_timezone_change(self, callback: types.CallbackQuery, state: FSMContext):
        text = (
            "🌍 Укажите ваш часовой пояс в формате GMT±X\n\n"
            "Выберите из популярных вариантов или введите свой:"
        )
        
        # Создаем кнопки с популярными часовыми поясами
        buttons = [
            [
                types.InlineKeyboardButton(text="GMT+3 (Москва)", callback_data="timezone_GMT+3"),
                types.InlineKeyboardButton(text="GMT+4 (Самара)", callback_data="timezone_GMT+4")
            ],
            [
                types.InlineKeyboardButton(text="GMT+5 (Екатеринбург)", callback_data="timezone_GMT+5"),
                types.InlineKeyboardButton(text="GMT+6 (Омск)", callback_data="timezone_GMT+6")
            ],
            [
                types.InlineKeyboardButton(text="GMT+7 (Новосибирск)", callback_data="timezone_GMT+7"),
                types.InlineKeyboardButton(text="GMT+8 (Иркутск)", callback_data="timezone_GMT+8")
            ],
            [
                types.InlineKeyboardButton(text="GMT+9 (Якутск)", callback_data="timezone_GMT+9"),
                types.InlineKeyboardButton(text="GMT+10 (Владивосток)", callback_data="timezone_GMT+10")
            ],
            [
                types.InlineKeyboardButton(text="GMT+11 (Магадан)", callback_data="timezone_GMT+11"),
                types.InlineKeyboardButton(text="GMT+12 (Камчатка)", callback_data="timezone_GMT+12")
            ],
            [
                types.InlineKeyboardButton(
                    text="✅ Сохранить",
                    callback_data="save_timezone"
                )
            ]
        ]
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(TimezoneStates.waiting_for_timezone)
        await callback.answer()

    async def process_timezone_setting(self, message: types.Message, state: FSMContext):
        timezone_str = message.text.strip().upper()
        
        if not timezone_str.startswith('GMT') or len(timezone_str) < 4:
            await message.answer(
                "❌ Неверный формат. Используйте формат GMT±X (например, GMT+3)\n"
                "Или выберите из предложенных вариантов."
            )
            return
        
        try:
            offset = int(timezone_str[3:])
            if offset < -12 or offset > 14:
                raise ValueError("Недопустимое смещение")
            
            timezone_name = f"Etc/GMT{'-' if offset > 0 else '+'}{abs(offset)}"
            self.db.set_user_timezone(message.from_user.id, timezone_name)
            
            # Отправляем новое сообщение с обновленными настройками
            text = f"⚙️ Настройки\n\n🌍 Часовой пояс: {timezone_str}"
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="🔄 менить часовой пояс",
                    callback_data="change_timezone"
                )]
            ])
            
            await message.answer(text, reply_markup=keyboard)
            await state.clear()
            
        except ValueError:
            await message.answer(
                "❌ Неверный формат часового пояса.\n"
                "Используйте формат GMT±X, где X - число от -12 до +14\n"
                "Или выберите из предложенных вариантов."
            )

    async def save_timezone(self, callback: types.CallbackQuery, state: FSMContext):
        user_timezone = self.db.get_user_timezone(callback.from_user.id)
        # Конвертируем Etc/GMT+3 в GMT-3
        display_timezone = user_timezone.replace('Etc/', '')
        if display_timezone.startswith('GMT+'):
            display_timezone = 'GMT' + display_timezone[4:].replace('+', '-')
        elif display_timezone.startswith('GMT-'):
            display_timezone = 'GMT' + display_timezone[4:].replace('-', '+')
        
        text = f"⚙️ Настройки\n\n🌍 Часовой пояс: {display_timezone}"
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="🔄 Сменить часовой пояс",
                callback_data="change_timezone"
            )]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await state.clear()
        await callback.answer("Настройки сохранены")

    async def handle_voice(self, message: types.Message):
        try:
            file = await self.bot.get_file(message.voice.file_id)
            file_path = file.file_path
            voice_ogg = "voice.ogg"
            voice_wav = "voice.wav"
            
            # Скачиваем файл
            await self.bot.download_file(file_path, voice_ogg)
            
            # Конвертируем и распозам
            self.speech_recognizer.convert_ogg_to_wav(voice_ogg, voice_wav)
            recognized_text = self.speech_recognizer.transcribe(voice_wav)
            
            # Получаем данные о событии
            user_timezone = self.db.get_user_timezone(message.from_user.id)
            event_data = await self.event_extractor.extract_event_data(recognized_text, user_timezone)
            
            # Сначала сохраняем напоминание и получаем его ID
            reminder_id = self.db.save_reminder(
                message.from_user.id,
                event_data["description"],
                event_data["datetime"]
            )
            
            # Создаем клавиатуру с кнопкой отмены
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"cancel_{reminder_id}"
                )]
            ])
            
            # Отправляем подтверждение
            formatted_datetime = self.format_datetime(event_data['datetime'], user_timezone)
            text = (
                f"✅ Нпоминание создано!\n\n"
                f"Я распознал: {recognized_text}\n\n"
                f"Событие: {event_data['description']}\n"
                f"Дата и время: {formatted_datetime}"
            )
            await message.answer(text, reply_markup=keyboard)
            
            # Планируем уведомления с существующим reminder_id
            self.notification_manager.schedule_notifications(
                message.from_user.id,
                event_data,
                user_timezone,
                reminder_id
            )
            
        except Exception as e:
            await message.answer(f"❌ Произошла ошибка: {str(e)}")
        finally:
            # Удаляем временные файлы
            for file in [voice_ogg, voice_wav]:
                if os.path.exists(file):
                    os.remove(file)

    async def handle_text(self, message: types.Message, state: FSMContext):
        # Проверяем состояние через переданный state
        current_state = await state.get_state()
        print(f"handle_text: текущее состояние {current_state}")
        
        if current_state in [ManualReminderStates.waiting_for_description.state, 
                           ManualReminderStates.waiting_for_datetime.state]:
            # Если пользователь в процессе мануального создания,
            # не обрабатываем сообщение как обычный текст
            print("handle_text: пропускаем обработку из-за состояния создания")
            return
        
        try:
            # Получаем данные о событии
            user_timezone = self.db.get_user_timezone(message.from_user.id)
            event_data = await self.event_extractor.extract_event_data(message.text, user_timezone)
            
            # Создаем напоминание и планируем уведомления
            reminder_id = self.db.save_reminder(
                message.from_user.id,
                event_data["description"],
                event_data["datetime"]
            )
            
            # Создаем клавиатуру с кнопкой отмены
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"cancel_{reminder_id}"
                )]
            ])
            
            # Отправляем подтверждение
            formatted_datetime = self.format_datetime(event_data['datetime'], user_timezone)
            text = (
                f"✅ Напоминание создано!\n\n"
                f"Событие: {event_data['description']}\n"
                f"Дата и время: {formatted_datetime}"
            )
            await message.answer(text, reply_markup=keyboard)
            
            # Планируем уведомления с существующим reminder_id
            self.notification_manager.schedule_notifications(
                message.from_user.id,
                event_data,
                user_timezone,
                reminder_id
            )
            
        except Exception as e:
            await message.answer(f"❌ Произошла ошибка: {str(e)}")

    async def cancel_reminder(self, callback_query: types.CallbackQuery):
        reminder_id = int(callback_query.data.split('_')[1])
        
        try:
            self.db.delete_reminder(reminder_id)
            await callback_query.message.edit_text(
                f"{callback_query.message.text}\n\n❌ Напоминание отменено!"
            )
            await callback_query.answer("Напоминание успешно отменено")
        except Exception as e:
            await callback_query.answer(f"Ошибка при отмене напоминания: {str(e)}")

    async def process_timezone_button(self, callback: types.CallbackQuery, state: FSMContext):
        timezone_str = callback.data.replace("timezone_", "")
        try:
            offset = int(timezone_str[3:])
            timezone_name = f"Etc/GMT{'-' if offset > 0 else '+'}{abs(offset)}"
            self.db.set_user_timezone(callback.from_user.id, timezone_name)
            
            text = f"⚙️ Настройки\n\n🌍 Часовой пояс: {timezone_str}"
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="🔄 Сменить часовой пояс",
                    callback_data="change_timezone"
                )]
            ])
            
            await callback.message.edit_text(text, reply_markup=keyboard)
            await state.clear()
            await callback.answer("Часовой пояс установлен")
            
        except Exception as e:
            await callback.answer(f"Ошибка при установке часового пояса: {str(e)}")

    async def manual_command(self, message: types.Message, state: FSMContext):
        print("Начато мануальное создание напоминания")
        text = (
            "📝 Создание напоминания вручную\n\n"
            "Шаг 1: Введите описание события\n"
            "Например: 'Встреча с врачом' или 'Позвонить маме'"
        )
        # Создаем inline кнопку отмены
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="❌ Отменить создание",
                callback_data="cancel_manual"
            )]
        ])
        await state.set_state(ManualReminderStates.waiting_for_description)
        await message.answer(text, reply_markup=keyboard)

    async def process_manual_description(self, message: types.Message, state: FSMContext):
        print(f"Получено описание: {message.text}")
        print(f"Текущее состояние: {await state.get_state()}")
        
        # Сохраняем описание
        await state.update_data(description=message.text)
        
        text = (
            "📅 Шаг 2: Введите дату и время в формате 'ДД.ММ.ГГГГ ЧЧ:ММ'\n"
            "Например: '25.11.2024 15:30'\n\n"
            "❗️ Важно: используйте точки для разделения дня/месяца/года\n"
            "и двоеточие для разделения часов и минут"
        )
        
        # Создаем inline кнопку отмены
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="❌ Отменить создание",
                callback_data="cancel_manual"
            )]
        ])
        
        print("Отправляем запрос даты и времени")
        await state.set_state(ManualReminderStates.waiting_for_datetime)
        await message.answer(text, reply_markup=keyboard)

    async def process_manual_datetime(self, message: types.Message, state: FSMContext):
        try:
            # Получаем сохраненное описание
            data = await state.get_data()
            description = data['description']
            
            # Парсим дату и время
            try:
                dt = datetime.strptime(message.text, '%d.%m.%Y %H:%M')
            except ValueError:
                await message.answer(
                    "❌ Неверный формат даты и времени.\n"
                    "Используйте формат ДД.ММ.ГГГГ ЧЧ:ММ\n"
                    "Например: 25.11.2024 15:30"
                )
                return
            
            # Проверяем, что дата не в прошлом
            user_timezone = self.db.get_user_timezone(message.from_user.id)
            local_tz = pytz.timezone(user_timezone)
            current_time = datetime.now(local_tz)
            
            # Локализуем введенное время
            local_dt = local_tz.localize(dt)
            
            if local_dt < current_time:
                await message.answer(
                    "❌ Нельзя создать напоминание на прошедшее время.\n"
                    "Пожалуйста, введите будущую дату и время."
                )
                return
            
            # Конвертируем в UTC для сохранения
            utc_dt = local_dt.astimezone(pytz.UTC)
            
            # Создаем event_data для создания напоминания
            event_data = {
                "description": description,
                "datetime": utc_dt.strftime('%Y-%m-%d %H:%M')
            }
            
            # Создаем напоминание
            reminder_id = self.db.save_reminder(
                message.from_user.id,
                event_data["description"],
                event_data["datetime"]
            )
            
            # Создаем клавиатуру с кнопкой отмены
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"cancel_{reminder_id}"
                )]
            ])
            
            # Отправляем подтверждение
            formatted_datetime = self.format_datetime(event_data['datetime'], user_timezone)
            text = (
                f"✅ Напоминание создано вручную!\n\n"
                f"Событие: {event_data['description']}\n"
                f"Дата и время: {formatted_datetime}"
            )
            await message.answer(text, reply_markup=keyboard)
            
            # Планируем уведомления
            self.notification_manager.schedule_notifications(
                message.from_user.id,
                event_data,
                user_timezone,
                reminder_id
            )
            
            # Очищаем состояни
            await state.clear()
            
        except Exception as e:
            await message.answer(
                f"❌ Произошла ошибка: {str(e)}\n"
                "Попробуйте еще раз или используйте /cancel для отмены",
                reply_markup=types.ReplyKeyboardMarkup(
                    keyboard=[[types.KeyboardButton(text="/cancel")]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
            )

    async def cancel_manual_callback(self, callback: types.CallbackQuery, state: FSMContext):
        current_state = await state.get_state()
        if current_state in [ManualReminderStates.waiting_for_description.state,
                            ManualReminderStates.waiting_for_datetime.state]:
            await state.clear()
            await callback.message.edit_text(
                "❌ Создание напоминания отменено.\n"
                "Вы можете начать заново с помощью команды /manual"
            )
            await callback.answer()
        else:
            await callback.answer("Нет активного процесса создания напоминания.")

    async def run(self):
        try:
            # Инициализируем планировщик уведомлений
            await self.notification_manager.init_scheduler()
            
            # Запускаем бота
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            print(f"Ошибка при запуске бота: {e}")
            if self.notification_manager.scheduler:
                self.notification_manager.scheduler.shutdown()
        finally:
            await self.bot.session.close()

if __name__ == "__main__":
    bot = ReminderBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nЗавершение работы бота...") 
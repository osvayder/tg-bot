#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NinjaOsvayder - Telegram бот для транскрипции видео и аудио
MVP версия: транскрипция видео/аудио через Google Cloud Speech-to-Text
"""

import os
import logging
import tempfile
from pathlib import Path
from datetime import datetime
import time

from telegram import Update, Message
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

import moviepy.editor as mp
from google.cloud import speech_v1
from google.oauth2 import service_account
from pydub import AudioSegment
from pydub.utils import make_chunks

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
SERVICE_ACCOUNT_FILE = 'service_account.json'
TEMP_DIR = Path('temp_files')
TEMP_DIR.mkdir(exist_ok=True)

# Максимальный размер файла для Telegram (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

class TranscriptionBot:
    def __init__(self):
        """Инициализация бота и Speech-to-Text клиента"""
        # Настройка Google Cloud Speech-to-Text
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE
        )
        self.speech_client = speech_v1.SpeechClient(credentials=credentials)
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        welcome_message = """
🥷 *NinjaOsvayder Bot* - Ваш персональный транскрибатор!

📹 *Что я умею:*
• Транскрибирую видео и аудио файлы
• Поддерживаю русский язык
• Обрабатываю длинные записи

📤 *Как использовать:*
Просто отправьте мне видео или аудио файл, и я верну вам полную транскрипцию!

⚡ *Команды:*
/start - Показать это сообщение
/help - Помощь по использованию
/status - Проверить статус бота

_Максимальный размер файла: 50 MB_
"""
        await update.message.reply_text(
            welcome_message, 
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
📖 *Помощь по использованию NinjaOsvayder Bot*

*Поддерживаемые форматы:*
• Видео: MP4, AVI, MOV, MKV, WebM
• Аудио: MP3, WAV, OGG, M4A, FLAC

*Процесс обработки:*
1️⃣ Отправьте видео/аудио файл боту
2️⃣ Бот скачает и обработает файл
3️⃣ Если это видео - извлечет аудио дорожку
4️⃣ Выполнит транскрипцию через Google Speech-to-Text
5️⃣ Отправит вам полный текст

*Ограничения:*
• Максимальный размер файла: 50 MB
• Длительность: до 60 минут
• Язык: русский (по умолчанию)

*Советы:*
• Для лучшего качества используйте записи с четкой речью
• Избегайте сильных фоновых шумов
• Оптимальный битрейт аудио: 16-48 kHz

_Есть вопросы? Напишите @osvayder_
"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status"""
        status_text = """
✅ *Статус бота: Активен*

🔧 *Системная информация:*
• Speech-to-Text: Google Cloud
• Версия: MVP 1.0
• Язык транскрипции: Русский
• Временные файлы: Автоочистка

🚀 *Готов к работе!*
"""
        await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)
    
    def extract_audio_from_video(self, video_path: str, audio_path: str):
        """Извлечение аудио из видео файла"""
        try:
            logger.info(f"Извлечение аудио из {video_path}")
            video = mp.VideoFileClip(video_path)
            audio = video.audio
            audio.write_audiofile(audio_path, logger=None)
            video.close()
            audio.close()
            logger.info(f"Аудио успешно извлечено: {audio_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при извлечении аудио: {e}")
            return False
    
    def convert_to_wav(self, input_path: str, output_path: str):
        """Конвертация аудио в WAV формат для Speech-to-Text"""
        try:
            logger.info(f"Конвертация в WAV: {input_path}")
            audio = AudioSegment.from_file(input_path)
            # Конвертируем в моно, 16kHz для оптимальной работы Speech-to-Text
            audio = audio.set_channels(1)
            audio = audio.set_frame_rate(16000)
            audio.export(output_path, format="wav")
            logger.info(f"Успешно конвертировано в WAV: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при конвертации в WAV: {e}")
            return False
    
    def transcribe_audio_chunk(self, audio_content: bytes) -> str:
        """Транскрибация одного фрагмента аудио"""
        try:
            audio = speech_v1.RecognitionAudio(content=audio_content)
            config = speech_v1.RecognitionConfig(
                encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code="ru-RU",
                enable_automatic_punctuation=True,
                enable_word_time_offsets=False,
                model="latest_long"
            )
            
            response = self.speech_client.recognize(config=config, audio=audio)
            
            transcript = ""
            for result in response.results:
                transcript += result.alternatives[0].transcript + " "
            
            return transcript.strip()
        except Exception as e:
            logger.error(f"Ошибка при транскрипции чанка: {e}")
            return ""
    
    def transcribe_long_audio(self, wav_path: str) -> str:
        """Транскрибация длинного аудио файла по частям"""
        try:
            logger.info(f"Начало транскрипции файла: {wav_path}")
            
            # Загружаем аудио
            audio = AudioSegment.from_wav(wav_path)
            
            # Разбиваем на чанки по 30 секунд
            chunk_length_ms = 30000
            chunks = make_chunks(audio, chunk_length_ms)
            
            full_transcript = []
            total_chunks = len(chunks)
            
            for i, chunk in enumerate(chunks, 1):
                logger.info(f"Обработка фрагмента {i}/{total_chunks}")
                
                # Экспортируем чанк в байты
                with tempfile.NamedTemporaryFile(suffix='.wav') as tmp_file:
                    chunk.export(tmp_file.name, format="wav")
                    with open(tmp_file.name, 'rb') as f:
                        chunk_bytes = f.read()
                
                # Транскрибируем чанк
                chunk_transcript = self.transcribe_audio_chunk(chunk_bytes)
                if chunk_transcript:
                    full_transcript.append(chunk_transcript)
                
                # Небольшая задержка между запросами
                time.sleep(0.5)
            
            result = " ".join(full_transcript)
            logger.info(f"Транскрипция завершена. Длина текста: {len(result)} символов")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при транскрипции длинного аудио: {e}")
            return ""
    
    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка видео файлов"""
        message = update.message
        
        # Проверка размера файла
        if message.video.file_size > MAX_FILE_SIZE:
            await message.reply_text(
                "❌ Файл слишком большой! Максимальный размер: 50 MB",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Отправляем уведомление о начале обработки
        status_msg = await message.reply_text(
            "📥 *Получен видео файл*\n⏳ Начинаю обработку...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # Создаем временные файлы
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_path = TEMP_DIR / f"video_{timestamp}.mp4"
            audio_path = TEMP_DIR / f"audio_{timestamp}.mp3"
            wav_path = TEMP_DIR / f"audio_{timestamp}.wav"
            
            # Скачиваем видео
            await status_msg.edit_text(
                "📥 *Скачивание видео...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            file = await context.bot.get_file(message.video.file_id)
            await file.download_to_drive(video_path)
            
            # Извлекаем аудио
            await status_msg.edit_text(
                "🎵 *Извлечение аудио дорожки...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            if not self.extract_audio_from_video(str(video_path), str(audio_path)):
                await status_msg.edit_text("❌ Ошибка при извлечении аудио")
                return
            
            # Конвертируем в WAV
            await status_msg.edit_text(
                "🔄 *Конвертация аудио...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            if not self.convert_to_wav(str(audio_path), str(wav_path)):
                await status_msg.edit_text("❌ Ошибка при конвертации аудио")
                return
            
            # Транскрибируем
            await status_msg.edit_text(
                "🎯 *Транскрипция аудио...*\n_Это может занять несколько минут_",
                parse_mode=ParseMode.MARKDOWN
            )
            
            transcript = self.transcribe_long_audio(str(wav_path))
            
            if not transcript:
                await status_msg.edit_text("❌ Не удалось транскрибировать аудио")
                return
            
            # Отправляем результат
            await status_msg.edit_text(
                "✅ *Транскрипция завершена!*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Если текст слишком длинный, разбиваем на части
            if len(transcript) > 4000:
                # Сохраняем в файл
                txt_path = TEMP_DIR / f"transcript_{timestamp}.txt"
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(f"Транскрипция видео от {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(transcript)
                
                # Отправляем файл
                with open(txt_path, 'rb') as f:
                    await message.reply_document(
                        f,
                        filename=f"transcript_{timestamp}.txt",
                        caption="📝 *Полная транскрипция видео*",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # Отправляем первые 4000 символов в сообщении
                preview = transcript[:3900] + "...\n\n_Полный текст в файле выше_"
                await message.reply_text(
                    f"📝 *Транскрипция (предпросмотр):*\n\n{preview}",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Удаляем временный текстовый файл
                os.remove(txt_path)
            else:
                # Отправляем весь текст в сообщении
                await message.reply_text(
                    f"📝 *Транскрипция:*\n\n{transcript}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке видео: {e}")
            await status_msg.edit_text(
                f"❌ *Произошла ошибка:*\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN
            )
        
        finally:
            # Очищаем временные файлы
            for path in [video_path, audio_path, wav_path]:
                if path.exists():
                    try:
                        os.remove(path)
                    except:
                        pass
    
    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка аудио файлов"""
        message = update.message
        
        # Проверка размера файла
        audio = message.audio or message.voice
        if audio.file_size > MAX_FILE_SIZE:
            await message.reply_text(
                "❌ Файл слишком большой! Максимальный размер: 50 MB",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Отправляем уведомление о начале обработки
        status_msg = await message.reply_text(
            "🎵 *Получен аудио файл*\n⏳ Начинаю обработку...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # Создаем временные файлы
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_path = TEMP_DIR / f"audio_{timestamp}.ogg"
            wav_path = TEMP_DIR / f"audio_{timestamp}.wav"
            
            # Скачиваем аудио
            await status_msg.edit_text(
                "📥 *Скачивание аудио...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            file = await context.bot.get_file(audio.file_id)
            await file.download_to_drive(audio_path)
            
            # Конвертируем в WAV
            await status_msg.edit_text(
                "🔄 *Конвертация аудио...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            if not self.convert_to_wav(str(audio_path), str(wav_path)):
                await status_msg.edit_text("❌ Ошибка при конвертации аудио")
                return
            
            # Транскрибируем
            await status_msg.edit_text(
                "🎯 *Транскрипция аудио...*\n_Это может занять несколько минут_",
                parse_mode=ParseMode.MARKDOWN
            )
            
            transcript = self.transcribe_long_audio(str(wav_path))
            
            if not transcript:
                await status_msg.edit_text("❌ Не удалось транскрибировать аудио")
                return
            
            # Отправляем результат
            await status_msg.edit_text(
                "✅ *Транскрипция завершена!*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Если текст слишком длинный, разбиваем на части
            if len(transcript) > 4000:
                # Сохраняем в файл
                txt_path = TEMP_DIR / f"transcript_{timestamp}.txt"
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(f"Транскрипция аудио от {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(transcript)
                
                # Отправляем файл
                with open(txt_path, 'rb') as f:
                    await message.reply_document(
                        f,
                        filename=f"transcript_{timestamp}.txt",
                        caption="📝 *Полная транскрипция аудио*",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # Отправляем первые 4000 символов в сообщении
                preview = transcript[:3900] + "...\n\n_Полный текст в файле выше_"
                await message.reply_text(
                    f"📝 *Транскрипция (предпросмотр):*\n\n{preview}",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Удаляем временный текстовый файл
                os.remove(txt_path)
            else:
                # Отправляем весь текст в сообщении
                await message.reply_text(
                    f"📝 *Транскрипция:*\n\n{transcript}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке аудио: {e}")
            await status_msg.edit_text(
                f"❌ *Произошла ошибка:*\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN
            )
        
        finally:
            # Очищаем временные файлы
            for path in [audio_path, wav_path]:
                if path.exists():
                    try:
                        os.remove(path)
                    except:
                        pass

def main():
    """Основная функция запуска бота"""
    # Загружаем переменные окружения из .env файла
    from dotenv import load_dotenv
    load_dotenv()
    
    # Получаем токен
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        logger.error("BOT_TOKEN не установлен! Проверьте файл .env")
        return
    
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        logger.error(f"Файл {SERVICE_ACCOUNT_FILE} не найден!")
        return
    
    # Создаем экземпляр бота
    bot = TranscriptionBot()
    
    # Создаем приложение
    application = Application.builder().token(bot_token).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("status", bot.status_command))
    
    # Регистрируем обработчики медиа файлов
    application.add_handler(MessageHandler(filters.VIDEO, bot.handle_video))
    application.add_handler(MessageHandler(filters.AUDIO, bot.handle_audio))
    application.add_handler(MessageHandler(filters.VOICE, bot.handle_audio))
    
    # Запускаем бота
    logger.info("🚀 NinjaOsvayder Bot запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

import functools
import logging
import os
import psutil
import re
import sqlite3
import asyncio
from dotenv import load_dotenv
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import List
from telegram import Document, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, ConversationHandler, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.warnings import PTBUserWarning
from warnings import filterwarnings

# Disable useless warnings
filterwarnings(action="ignore", message=r".*CallbackQueryHandler",
               category=PTBUserWarning)

# Configure logging
logger = logging.getLogger(__name__)


class Config:
    """
    Manages loading and accessing configuration from environment variables.
    """

    def __init__(self, dotenv_path: str = ".env"):
        load_dotenv(dotenv_path)

        self.TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN")
        self.PAYPAL_LINK: str = os.getenv("PAYPAL_LINK")
        
        self.M_COLORS: List[str] = os.getenv("M_COLORS").split(',')
        
        self.DATABASE_NAME: Path = Path(os.getenv("DATABASE_NAME"))
        self.LOGFILE_NAME: Path = Path(os.getenv("LOGFILE_NAME"))

        self.MARKERS_COLOR_BUTTON: str = os.getenv("MARKERS_COLOR_BUTTON")
        self.CHAPTERS_SEPARATOR_BUTTON: str = os.getenv(
            "CHAPTERS_SEPARATOR_BUTTON")
        self.HELP_BUTTON: str = os.getenv("HELP_BUTTON")

        self.GLOBAL_TTL: int = int(os.getenv("GLOBAL_TTL"))
        self.RAM_THRESHOLD: int = int(os.getenv("RAM_THRESHOLD"))

        self.MARKERS_COLOR_PATTERN: str = os.getenv("MARKERS_COLOR_PATTERN")

        self.COLOR_TIMEOUT_MESSAGE: str = os.getenv(
            "COLOR_TIMEOUT_MESSAGE").format(ttl=self.GLOBAL_TTL)
        self.SEPARATOR_TIMEOUT_MESSAGE: str = os.getenv(
            "SEPARATOR_TIMEOUT_MESSAGE").format(ttl=self.GLOBAL_TTL)
        self.ERROR_MESSAGE: str = os.getenv("ERROR_MESSAGE")
        self.RAM_FULL_MESSAGE: str = os.getenv("RAM_FULL_MESSAGE")
        
        self.START_MESSAGE: str = os.getenv("START_MESSAGE").format(
            MARKERS_COLOR_BUTTON=self.MARKERS_COLOR_BUTTON,
            CHAPTERS_SEPARATOR_BUTTON=self.CHAPTERS_SEPARATOR_BUTTON,
            GLOBAL_TTL=self.GLOBAL_TTL,
            HELP_BUTTON=self.HELP_BUTTON
        )
        self.SELECT_MARKERS_COLOR_MESSAGE: str = os.getenv(
            "SELECT_MARKERS_COLOR_MESSAGE")
        self.INSERT_SEPARATOR_MESSAGE: str = os.getenv(
            "INSERT_SEPARATOR_MESSAGE")
        self.EDL_FILE_ERROR_MESSAGE: str = os.getenv("EDL_FILE_ERROR_MESSAGE")
        self.UPLOAD_EDL_FILE_MESSAGE: str = os.getenv(
            "UPLOAD_EDL_FILE_MESSAGE")
        self.HELP_MESSAGE: str = os.getenv(
            "HELP_MESSAGE").format(GLOBAL_TTL=self.GLOBAL_TTL)
        self.MARKERS_COLOR_UPDATED_MESSAGE: str = os.getenv(
            "MARKERS_COLOR_UPDATED_MESSAGE")
        self.CHAPTERS_SEPARATOR_UPDATED_MESSAGE: str = os.getenv(
            "CHAPTERS_SEPARATOR_UPDATED_MESSAGE")
        self.END_CONVERSATION_MESSAGE: str = os.getenv(
            "END_CONVERSATION_MESSAGE")
        self.DONATE_MESSAGE: str = os.getenv("DONATE_MESSAGE")


class DatabaseManager:
    """
    Manages all SQLite database operations.
    """

    def __init__(self, db_name: str):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_db()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def _execute(self, query, params=(), commit=False, fetchone=False, fetchall=False):
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                if commit:
                    return cursor.lastrowid
                if fetchone:
                    return cursor.fetchone()
                if fetchall:
                    return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}", exc_info=True)
            return None

    def create_db(self):
        self._execute('''
            CREATE TABLE IF NOT EXISTS choices (user_id INTEGER PRIMARY KEY, m_color TEXT DEFAULT 'Blue', c_separator TEXT DEFAULT '-')
        ''')

    def add_user(self, user_id: int): self._execute(
        'INSERT OR IGNORE INTO choices (user_id) VALUES (?)', (user_id,), commit=True)

    def get_choices(self, user_id: int) -> sqlite3.Row: return self._execute(
        'SELECT * FROM choices WHERE user_id = ?', (user_id,), fetchone=True)

    def update_markers_color(self, user_id: int, m_color: str): self._execute(
        'UPDATE choices SET m_color = ? WHERE user_id = ?', (m_color, user_id), commit=True)

    def update_chapters_separator(self, user_id: int, c_separator: str): self._execute(
        'UPDATE choices SET c_separator = ? WHERE user_id = ?', (c_separator, user_id), commit=True)


def setup_logging(logfile_name: str):
    """Configures root-level logging."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        handlers=[
            TimedRotatingFileHandler(
                filename=logfile_name,
                when="W0",
                interval=1,
                backupCount=3
            ),
            logging.StreamHandler()
        ]
    )
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.addFilter(
        lambda record: "getUpdates" not in record.getMessage())


async def keep_alive():
    while True:
        logger.info("Polling...")
        await asyncio.sleep(600)


def handle_errors(func):
    """
    Decorator for centralized error handling in bot handlers.
    """
    @functools.wraps(func)
    async def wrapper(self: 'DVChapterBot', update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id if update.effective_user else "N/A"
        try:
            return await func(self, update, context, *args, **kwargs)
        except Exception:
            logger.error(
                f"Error in {func.__name__} for {user_id}:", exc_info=True)
            error_message = self.config.ERROR_MESSAGE
            await self.send_reply(update, error_message)

            # If the handler is part of a Conversation, terminate it
            return ConversationHandler.END
    return wrapper


def function_setup(func):
    """
    Decorator to handle common function setup: logging, and adding user to DB.
    """
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id if update.effective_user else "N/A"
        logger.info(f"{func.__name__} for {user_id}")
        self.db.add_user(user_id)
        return await func(self, update, context, *args, **kwargs)
    return wrapper


class DVChapterBot:
    """
    Main Bot class. Manages logic, handlers, and execution.
    """
    # Conversation states
    CHANGE_MARKERS_COLOR = range(1)
    CHANGE_CHAPTERS_SEPARATOR = range(1)
    TIMEOUT = ConversationHandler.TIMEOUT
    END = ConversationHandler.END

    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.application = Application.builder().token(
            self.config.TELEGRAM_BOT_TOKEN).build()

    # --------------- UTILITY METHODS ----------------

    async def _create_reply_keyboard(self, user_id: int) -> ReplyKeyboardMarkup:
        choice = self.db.get_choices(user_id)
        m_color = choice['m_color']
        c_separator = choice['c_separator']

        reply_keyboard = [
            [f'{self.config.MARKERS_COLOR_BUTTON}\n[ {m_color} ]'],
            [f'{self.config.CHAPTERS_SEPARATOR_BUTTON}\n[ {c_separator} ]'],
            [self.config.HELP_BUTTON]
        ]
        return ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

    async def send_reply(self, update: Update, text: str, **kwargs):
        """Safely sends a reply message to an Update or CallbackQuery."""
        target_message = None
        user_id = None

        callback_query = update.callback_query
        if callback_query:
            await callback_query.answer()
            target_message = callback_query.message
            user_id = callback_query.from_user.id
        else:
            target_message = update.effective_message
            user_id = update.effective_user.id

        if target_message and user_id:
            reply_keyboard_markup = await self._create_reply_keyboard(user_id)
            kwargs.setdefault('reply_markup', reply_keyboard_markup)
            await target_message.reply_text(text, **kwargs)
        else:
            logger.warning(
                f"send_reply: Could not find target message or user_id.")

    async def _process_edl_file(self, user_id: int, file: Document) -> str:
        file_prep = await file.get_file()
        file_path = Path(await file_prep.download_to_drive())

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                return self._format_chapters(user_id, lines)
        finally:
            if file_path.exists():
                file_path.unlink()

    def _format_chapters(self, user_id: int, lines: List[str]) -> str:
        choices = self.db.get_choices(user_id)
        m_color = choices['m_color']
        c_separator = choices['c_separator']
        n_lines = len(lines)

        if n_lines < 6:
            return ''

        results = ['CAPITOLI\n--------------------']
        for i in range(3, n_lines, 3):
            if f'C:ResolveColor{m_color}' in lines[i+1]:
                m_time = re.search(r"\d{2}:\d{2}:\d{2}", lines[i])
                m_name = re.search(r"\|M:(.*?) \|D:", lines[i+1])
                if m_time and m_name:
                    results.append(
                        f'{m_time.group(0)} {c_separator} {m_name.group(1)}')

        return '\n'.join(results) if len(results) > 1 else ''

    async def _free_memory_check(self, update: Update) -> bool:
        user_id = update.effective_user.id
        logger.info(f"Memory free check for {user_id}")

        if psutil.virtual_memory().free / 1024 ** 2 < self.config.RAM_THRESHOLD:
            logger.warning(f"Memory full for {user_id}")
            await self.send_reply(update, self.config.RAM_FULL_MESSAGE)
            return False
        return True

    # --------------- COMMAND HANDLERS ----------------

    @handle_errors
    @function_setup
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = self.config.START_MESSAGE
        await self.send_reply(update, message)

    @handle_errors
    @function_setup
    async def change_markers_color_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        colors = self.config.M_COLORS
        inline_keyboard = [
            [InlineKeyboardButton(colors[i], callback_data=f'{colors[i]}'),
             InlineKeyboardButton(colors[i+1], callback_data=f'{colors[i+1]}')]
            for i in range(0, len(colors), 2)
        ]
        if len(colors) % 2 != 0:
            inline_keyboard.append([InlineKeyboardButton(
                colors[-1], callback_data=f'{colors[-1]}')])

        inline_keyboard_markup = InlineKeyboardMarkup(inline_keyboard)
        await self.send_reply(update, self.config.SELECT_MARKERS_COLOR_MESSAGE, reply_markup=inline_keyboard_markup)
        return self.CHANGE_MARKERS_COLOR

    @handle_errors
    @function_setup
    async def change_chapters_separator_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await self.send_reply(update, self.config.INSERT_SEPARATOR_MESSAGE)
        return self.CHANGE_CHAPTERS_SEPARATOR

    @handle_errors
    @function_setup
    async def upload_file_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._free_memory_check(update):
            return

        file = update.message.document
        if Path(file.file_name).suffix == '.edl':
            result = await self._process_edl_file(update.effective_user.id, file)
            if result:
                await self.send_reply(update, result)
            else:
                await self.send_reply(update, self.config.EDL_FILE_ERROR_MESSAGE)
        else:
            await self.send_reply(update, self.config.UPLOAD_EDL_FILE_MESSAGE)

    @handle_errors
    @function_setup
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = self.config.HELP_MESSAGE
        await self.send_reply(update, message)

    @handle_errors
    @function_setup
    async def donate_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        inline_keyboard = [[InlineKeyboardButton("❤️ Donate via PayPal ❤️", url=self.config.PAYPAL_LINK)]]
        inline_keyboard_markup = InlineKeyboardMarkup(inline_keyboard)
        await self.send_reply(update, self.config.DONATE_MESSAGE, reply_markup=inline_keyboard_markup)

    # --------------- CALLBACK HANDLERS ----------------

    @handle_errors
    @function_setup
    async def change_markers_color_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        m_color = query.data

        self.db.update_markers_color(update.effective_user.id, m_color)
        await self.send_reply(update, self.config.MARKERS_COLOR_UPDATED_MESSAGE.format(m_color=m_color))
        return self.END

    @handle_errors
    @function_setup
    async def change_chapters_separator_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        c_separator = update.message.text

        self.db.update_chapters_separator(
            update.effective_user.id, c_separator)
        await self.send_reply(update, self.config.CHAPTERS_SEPARATOR_UPDATED_MESSAGE.format(c_separator=c_separator))
        return self.END

    @handle_errors
    @function_setup
    async def end_conversation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await self.send_reply(update, self.config.END_CONVERSATION_MESSAGE)
        return self.END

    @handle_errors
    @function_setup
    async def color_timeout_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = self.config.COLOR_TIMEOUT_MESSAGE.format(
            ttl=self.config.GLOBAL_TTL)

        await self.send_reply(update, message)

    @handle_errors
    @function_setup
    async def separator_timeout_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = self.config.SEPARATOR_TIMEOUT_MESSAGE.format(
            ttl=self.config.GLOBAL_TTL)

        await self.send_reply(update, message)

    # --------------- BOT SETUP ----------------

    def _setup_markers_color_handler(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[
                CommandHandler("color", self.change_markers_color_command),
                MessageHandler(filters.Regex(
                    f"^{self.config.MARKERS_COLOR_BUTTON}"), self.change_markers_color_command)
            ],
            states={
                self.CHANGE_MARKERS_COLOR: [
                    CallbackQueryHandler(
                        self.change_markers_color_callback, pattern=self.config.MARKERS_COLOR_PATTERN)
                ],
                self.TIMEOUT: [
                    MessageHandler(filters.ALL, self.color_timeout_callback),
                    CallbackQueryHandler(self.color_timeout_callback)
                ]
            },
            fallbacks=[
                CommandHandler("color", self.change_markers_color_command),
                MessageHandler(filters.Regex(
                    f"^{self.config.MARKERS_COLOR_BUTTON}"), self.change_markers_color_command),
                CommandHandler("end", self.end_conversation_callback),
            ],
            conversation_timeout=self.config.GLOBAL_TTL
        )

    def _setup_chapters_separator_handler(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[
                CommandHandler(
                    "separator", self.change_chapters_separator_command),
                MessageHandler(filters.Regex(
                    f"^{self.config.CHAPTERS_SEPARATOR_BUTTON}"), self.change_chapters_separator_command)
            ],
            states={
                self.CHANGE_CHAPTERS_SEPARATOR: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(
                        f"^({self.config.CHAPTERS_SEPARATOR_BUTTON}|{self.config.MARKERS_COLOR_BUTTON}|{self.config.HELP_BUTTON})"), self.change_chapters_separator_callback)
                ],
                self.TIMEOUT: [
                    MessageHandler(
                        filters.ALL, self.separator_timeout_callback),
                    CallbackQueryHandler(self.separator_timeout_callback)
                ]
            },
            fallbacks=[
                CommandHandler(
                    "separator", self.change_chapters_separator_command),
                MessageHandler(filters.Regex(
                    f"^{self.config.CHAPTERS_SEPARATOR_BUTTON}"), self.change_chapters_separator_command),
                CommandHandler("end", self.end_conversation_callback),
            ],
            conversation_timeout=self.config.GLOBAL_TTL
        )

    def _setup_handlers(self):
        # Command handlers
        start_handler = CommandHandler("start", self.start_command)
        file_handler = MessageHandler(
            filters.ATTACHMENT, self.upload_file_command)
        help_handlers = [
            CommandHandler("help", self.help_command),
            MessageHandler(filters.Regex(
                f"^{self.config.HELP_BUTTON}$"), self.help_command)
        ]
        donate_handler = CommandHandler("donate", self.donate_command)

        # Conversation handlers
        markers_color_handler = self._setup_markers_color_handler()
        chapters_separator_handler = self._setup_chapters_separator_handler()

        self.application.add_handler(start_handler)
        self.application.add_handler(markers_color_handler)
        self.application.add_handler(chapters_separator_handler)
        self.application.add_handler(file_handler)
        self.application.add_handlers(help_handlers)
        self.application.add_handler(donate_handler)

    async def run(self):
        """Start the bot"""
        logger.info("Handler setup...")
        self._setup_handlers()

        app = self.application
        try:
            logger.info("Bot startup...")
            await asyncio.gather(app.initialize())
            await asyncio.gather(app.start())
            await asyncio.gather(app.updater.start_polling(allowed_updates=Update.ALL_TYPES))
            await asyncio.Future()
        except asyncio.CancelledError:
            logger.info("Bot run cancelled")
        finally:
            logger.info("Bot shutdown...")
            await asyncio.gather(app.updater.stop())
            await asyncio.gather(app.stop())
            await asyncio.gather(app.shutdown())


async def main() -> None:
    try:
        config = Config()
        setup_logging(config.LOGFILE_NAME)
        with DatabaseManager(config.DATABASE_NAME) as db:
            bot = DVChapterBot(config, db)
            
            loop = asyncio.get_event_loop()
            loop.create_task(keep_alive())
            
            await bot.run()

    except ValueError as e:
        logger.critical(f"Configuration error: {e}")
    except Exception as e:
        logger.critical("Critical error during bot startup:", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutdown forced by user.")

import os
import tempfile
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv
from vision import (
    calibrate_board_rect,
    confirm_board_rect,
    get_board_rect,
    reset_board_rect,
    get_board_auto,
    get_board_manual
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

# Простые состояния
class States(StatesGroup):
    need_position = State()      # Нужна калибровка положения
    ready_auto = State()         # Готов, авто-режим
    ready_manual = State()       # Готов, ждём фото для ручного режима
    waiting_coords = State()     # Получили фото, ждём координаты

storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

# Клавиатуры
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Сбросить калибровку")],
            [KeyboardButton(text="🎯 Авто режим"), KeyboardButton(text="✋ Ручной режим")]
        ],
        resize_keyboard=True
    )

kb_calibrate = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
    ],
    resize_keyboard=True
)


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(States.need_position)
    await message.answer(
        "Привет! Пришли скриншот Block Blast — я найду игровое поле.",
        reply_markup=kb_calibrate
    )


@dp.message(F.text == "🔄 Сбросить калибровку")
async def cmd_reset(message: types.Message, state: FSMContext):
    reset_board_rect(message.chat.id)
    await state.set_state(States.need_position)
    await message.answer(
        "Калибровка сброшена. Пришли новый скриншот.",
        reply_markup=kb_calibrate
    )


# === КАЛИБРОВКА ПОЛОЖЕНИЯ ===

@dp.message(States.need_position, F.photo)
async def calibrate_position(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        await bot.download(photo, destination=tmp.name)
        tmp_path = tmp.name
    
    await state.update_data(temp_photo=tmp_path)
    
    try:
        board_img_path, rect = calibrate_board_rect(tmp_path, message.chat.id)
        
        await message.answer_photo(
            FSInputFile(board_img_path),
            caption=f"Найдено поле: {rect}\n\nЭто правильное поле?",
            reply_markup=kb_calibrate
        )
        
        os.unlink(board_img_path)
        
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПопробуй другой скриншот.")


@dp.message(States.need_position, F.text.in_(["✅ Да", "да", "yes", "д", "y"]))
async def confirm_yes(message: types.Message, state: FSMContext):
    confirm_board_rect(message.chat.id, confirmed=True)
    await state.set_state(States.ready_auto)
    await message.answer(
        "✅ Положение сохранено!\n"
        "🎯 Авто режим: просто присылай скриншоты\n"
        "✋ Ручной режим: нажми кнопку и укажи пустую клетку",
        reply_markup=get_main_kb()
    )


@dp.message(States.need_position, F.text.in_(["❌ Нет", "нет", "no", "н", "n"]))
async def confirm_no(message: types.Message, state: FSMContext):
    await message.answer("Пришли другой скриншот.", reply_markup=kb_calibrate)


# === ПЕРЕКЛЮЧЕНИЕ РЕЖИМОВ ===

@dp.message(F.text == "🎯 Авто режим")
async def set_auto_mode(message: types.Message, state: FSMContext):
    if get_board_rect(message.chat.id) is None:
        await message.answer("Сначала нужна калибровка. Отправь /start")
        return
    
    await state.set_state(States.ready_auto)
    await message.answer(
        "🎯 Авто режим активирован.\nПросто присылай скриншоты.",
        reply_markup=get_main_kb()
    )


@dp.message(F.text == "✋ Ручной режим")
async def set_manual_mode(message: types.Message, state: FSMContext):
    if get_board_rect(message.chat.id) is None:
        await message.answer("Сначала нужна калибровка. Отправь /start")
        return
    
    await state.set_state(States.ready_manual)
    await message.answer(
        "✋ Ручной режим.\nПришли скриншот и укажи пустую клетку (1-8, например: 3 5)",
        reply_markup=get_main_kb()
    )


# === АВТО РЕЖИМ ===

@dp.message(States.ready_auto, F.photo)
async def auto_recognize(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        await bot.download(photo, destination=tmp.name)
        tmp_path = tmp.name
    
    try:
        board = get_board_auto(tmp_path, message.chat.id)
        
        lines = []
        for i, r in enumerate(board):
            line = ''.join(['⬛' if x else '⬜' for x in r])
            lines.append(f"{i+1}:{line}")
        
        result_text = '\n'.join(lines)
        await message.answer(
            f"<pre>{result_text}</pre>\n\n"
            f"Если неверно — переключись в ✋ Ручной режим",
            parse_mode='HTML',
            reply_markup=get_main_kb()
        )
        
    except Exception as e:
        await message.answer(f"Ошибка: {e}", reply_markup=get_main_kb())
    
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# === РУЧНОЙ РЕЖИМ ===

@dp.message(States.ready_manual, F.photo)
async def manual_photo(message: types.Message, state: FSMContext):
    """Получили фото в ручном режиме — сохраняем и ждём координаты"""
    photo = message.photo[-1]
    
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        await bot.download(photo, destination=tmp.name)
        tmp_path = tmp.name
    
    await state.update_data(manual_photo=tmp_path)
    await state.set_state(States.waiting_coords)
    await message.answer("Теперь напиши координаты пустой клетки (строка столбец, 1-8)")


@dp.message(States.waiting_coords, F.text)
async def manual_coords(message: types.Message, state: FSMContext):
    """Получили координаты — распознаём"""
    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            raise ValueError
        row, col = int(parts[0]), int(parts[1])
        if not (1 <= row <= 8 and 1 <= col <= 8):
            raise ValueError
    except:
        await message.answer("Неверный формат. Введи: строка столбец (1-8), например: 3 5")
        return
    
    data = await state.get_data()
    tmp_path = data.get('manual_photo')
    
    if not tmp_path or not os.path.exists(tmp_path):
        await message.answer("Ошибка: фото не найдено. Верниcь в ✋ Ручной режим")
        await state.set_state(States.ready_manual)
        return
    
    try:
        board = get_board_manual(tmp_path, message.chat.id, row, col)
        
        lines = []
        for i, r in enumerate(board):
            line = ''.join(['⬛' if x else '⬜' for x in r])
            lines.append(f"{i+1}:{line}")
        
        result_text = '\n'.join(lines)
        await message.answer(
            f"Ручной режим (пустая: {row} {col}):\n<pre>{result_text}</pre>",
            parse_mode='HTML',
            reply_markup=get_main_kb()
        )
        
    except Exception as e:
        await message.answer(f"Ошибка: {e}", reply_markup=get_main_kb())
    
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        await state.set_state(States.ready_manual)  # Остаёмся в ручном режиме


# === ОБРАБОТКА ТЕКСТА В НЕПРАВИЛЬНЫХ СОСТОЯНИЯХ ===

@dp.message(States.ready_auto, F.text)
async def ignore_text_in_auto(message: types.Message):
    """В авто режиме игнорируем текст, напоминаем про фото"""
    await message.answer("В авто режиме просто присылай скриншот. Или нажми ✋ Ручной режим")


@dp.message(States.ready_manual, F.text)
async def ignore_text_in_manual(message: types.Message):
    """В ручном режиме без фото — напоминаем"""
    await message.answer("Сначала пришли скриншот, потом укажи координаты. Или нажми 🎯 Авто режим")


def run_bot():
    dp.run_polling(bot)


if __name__ == "__main__":
    run_bot()
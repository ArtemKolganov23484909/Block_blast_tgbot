import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from engine import solve

TOKEN = "8725066411:AAGEfslRIVZR03uMXxLCYF0vE9Iu3ztzing"
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Пришли скриншот Block Blast")

@dp.message(lambda m: m.photo)
async def handle_photo(message: types.Message):
    # TODO: CV парсинг → grid + pieces
    # result = solve(grid, pieces)
    await message.answer("Пока тест: движок работает")

def run_bot():
    dp.run_polling(bot)
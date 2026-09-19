import asyncio
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ContentType, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from fastapi import FastAPI, Header, HTTPException, Request


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("pisnya-pro-tebe")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0") or 0)
WEBHOOK_BASE_URL = (
    os.environ.get("WEBHOOK_BASE_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")
    or ""
).rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "pisnya-pro-tebe-webhook").strip()
EXPRESS_STARS = int(os.environ.get("EXPRESS_STARS", "250"))
PREMIUM_STARS = int(os.environ.get("PREMIUM_STARS", "650"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


class Order(StatesGroup):
    recipient = State()
    occasion = State()
    name = State()
    language = State()
    style = State()
    voice = State()
    facts = State()
    forbidden = State()
    deadline = State()
    media = State()
    confirm = State()
    payment = State()


def db() -> sqlite3.Connection:
    connection = sqlite3.connect("orders.db")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            package TEXT NOT NULL,
            answers TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return connection


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Замовити персональну пісню", callback_data="order")],
        [InlineKeyboardButton(text="🎧 Послухати приклади", callback_data="examples")],
        [InlineKeyboardButton(text="💬 Зв’язатися з автором", callback_data="contact")],
        [InlineKeyboardButton(text="📦 Моє замовлення", callback_data="my_orders")],
    ])


def package_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚡ Експрес — {EXPRESS_STARS} ⭐", callback_data="package:express")],
        [InlineKeyboardButton(text=f"💎 Преміум — {PREMIUM_STARS} ⭐", callback_data="package:premium")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
    ])


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустити", callback_data="skip")]
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Усе правильно — оплатити", callback_data="pay")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")],
    ])


async def safe_edit(message: Message, text: str, markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        await message.answer(text, reply_markup=markup, parse_mode=ParseMode.HTML)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "<b>Пісня про тебе | Ksena Rika</b> 🎵\n\n"
        "Твоя історія, яка звучатиме назавжди ❤️\n"
        "Створимо персональну пісню для найдорожчої людини.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "home")
async def home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(callback.message, "Оберіть потрібний розділ:", main_menu())
    await callback.answer()


@router.callback_query(F.data == "order")
async def choose_package(callback: CallbackQuery) -> None:
    await safe_edit(
        callback.message,
        "Оберіть пакет:\n\n"
        "⚡ <b>Експрес</b> — один готовий варіант.\n"
        "💎 <b>Преміум</b> — глибша історія, уважне опрацювання та правки.",
        package_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("package:"))
async def package_selected(callback: CallbackQuery, state: FSMContext) -> None:
    package = callback.data.split(":", 1)[1]
    await state.set_data({"package": package, "media": []})
    await state.set_state(Order.recipient)
    await safe_edit(callback.message, "1/9. Для кого створюємо пісню?")
    await callback.answer()


@router.message(Order.recipient, F.text)
async def recipient(message: Message, state: FSMContext) -> None:
    await state.update_data(recipient=message.text)
    await state.set_state(Order.occasion)
    await message.answer("2/9. Яка подія? Наприклад: день народження, весілля, річниця.")


@router.message(Order.occasion, F.text)
async def occasion(message: Message, state: FSMContext) -> None:
    await state.update_data(occasion=message.text)
    await state.set_state(Order.name)
    await message.answer("3/9. Як звати людину? Напишіть також лагідні звертання.")


@router.message(Order.name, F.text)
async def name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text)
    await state.set_state(Order.language)
    await message.answer("4/9. Якою мовою має бути пісня?")


@router.message(Order.language, F.text)
async def language(message: Message, state: FSMContext) -> None:
    await state.update_data(language=message.text)
    await state.set_state(Order.style)
    await message.answer("5/9. Який стиль і настрій бажаєте?")


@router.message(Order.style, F.text)
async def style(message: Message, state: FSMContext) -> None:
    await state.update_data(style=message.text)
    await state.set_state(Order.voice)
    await message.answer("6/9. Який голос: жіночий чи чоловічий?")


@router.message(Order.voice, F.text)
async def voice(message: Message, state: FSMContext) -> None:
    await state.update_data(voice=message.text)
    await state.set_state(Order.facts)
    await message.answer(
        "7/9. Розкажіть вашу історію: важливі події, місця, спогади та слова, "
        "які обов’язково мають прозвучати."
    )


@router.message(Order.facts, F.text)
async def facts(message: Message, state: FSMContext) -> None:
    await state.update_data(facts=message.text)
    await state.set_state(Order.forbidden)
    await message.answer("8/9. Що не можна згадувати у пісні?", reply_markup=skip_keyboard())


@router.callback_query(Order.forbidden, F.data == "skip")
async def skip_forbidden(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(forbidden="—")
    await state.set_state(Order.deadline)
    await safe_edit(callback.message, "9/9. До якої дати потрібна готова пісня?")
    await callback.answer()


@router.message(Order.forbidden, F.text)
async def forbidden(message: Message, state: FSMContext) -> None:
    await state.update_data(forbidden=message.text)
    await state.set_state(Order.deadline)
    await message.answer("9/9. До якої дати потрібна готова пісня?")


@router.message(Order.deadline, F.text)
async def deadline(message: Message, state: FSMContext) -> None:
    await state.update_data(deadline=message.text)
    await state.set_state(Order.media)
    await message.answer(
        "Додайте фото або голосові повідомлення, якщо вони допоможуть передати історію. "
        "Можна надіслати декілька файлів. Коли завершите — натисніть «Готово».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="media_done")],
            [InlineKeyboardButton(text="Пропустити", callback_data="media_done")],
        ]),
    )


@router.message(Order.media, F.content_type.in_({ContentType.PHOTO, ContentType.VOICE, ContentType.AUDIO, ContentType.DOCUMENT}))
async def collect_media(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    media = list(data.get("media", []))
    media.append({"chat_id": message.chat.id, "message_id": message.message_id})
    await state.update_data(media=media)
    await message.answer("Файл додано ✅ Можете надіслати ще або натиснути «Готово».")


def summary(data: dict) -> str:
    package = "Експрес" if data.get("package") == "express" else "Преміум"
    return (
        f"<b>Пакет:</b> {package}\n"
        f"<b>Для кого:</b> {escape(str(data.get('recipient', '')))}\n"
        f"<b>Подія:</b> {escape(str(data.get('occasion', '')))}\n"
        f"<b>Ім’я:</b> {escape(str(data.get('name', '')))}\n"
        f"<b>Мова:</b> {escape(str(data.get('language', '')))}\n"
        f"<b>Стиль:</b> {escape(str(data.get('style', '')))}\n"
        f"<b>Голос:</b> {escape(str(data.get('voice', '')))}\n"
        f"<b>Історія:</b> {escape(str(data.get('facts', '')))}\n"
        f"<b>Не згадувати:</b> {escape(str(data.get('forbidden', '')))}\n"
        f"<b>Термін:</b> {escape(str(data.get('deadline', '')))}"
    )


@router.callback_query(Order.media, F.data == "media_done")
async def media_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(Order.confirm)
    await safe_edit(
        callback.message,
        "Перевірте замовлення:\n\n" + summary(data),
        confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(Order.confirm, F.data == "pay")
async def pay(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    package = data.get("package")
    stars = EXPRESS_STARS if package == "express" else PREMIUM_STARS
    title = "Експрес-пісня" if package == "express" else "Преміум-пісня"
    await state.set_state(Order.payment)
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=title,
        description="Персональна пісня від Ksena Rika",
        payload=f"song:{package}:{callback.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=stars)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    text = summary(data)
    with db() as connection:
        cursor = connection.execute(
            "INSERT INTO orders(user_id, username, package, answers, status, created_at) VALUES(?,?,?,?,?,?)",
            (
                message.from_user.id,
                message.from_user.username or "",
                data.get("package", ""),
                text,
                "paid",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        order_id = cursor.lastrowid
    if ADMIN_CHAT_ID:
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"🆕 <b>Оплачене замовлення №{order_id}</b>\n"
            f"Клієнт: @{escape(message.from_user.username or 'без username')}\n"
            f"User ID: <code>{message.from_user.id}</code>\n\n{text}",
            parse_mode=ParseMode.HTML,
        )
        for item in data.get("media", []):
            try:
                await bot.copy_message(ADMIN_CHAT_ID, item["chat_id"], item["message_id"])
            except Exception:
                log.exception("Could not forward attachment")
    await state.clear()
    await message.answer(
        f"Оплату отримано ✅ Ваше замовлення №{order_id} передано в роботу.",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(callback.message, "Замовлення скасовано.", main_menu())
    await callback.answer()


@router.callback_query(F.data == "examples")
async def examples(callback: CallbackQuery) -> None:
    example_links = [
        "https://vm.tiktok.com/ZN86VmECA/",
        "https://vm.tiktok.com/ZN86VyfMQ/",
        "https://vm.tiktok.com/ZN86VmUjW/",
        "https://vm.tiktok.com/ZN86VxAU5/",
        "https://vm.tiktok.com/ZN86VSAVm/",
        "https://vm.tiktok.com/ZN86VyoNg/",
        "https://vm.tiktok.com/ZN86VxABE/",
        "https://vm.tiktok.com/ZN86VATFs/",
        "https://vm.tiktok.com/ZN86VfjDc/",
        "https://vm.tiktok.com/ZN86VSrNj/",
        "https://vm.tiktok.com/ZN86V4rrm/",
    ]
    buttons = [
        InlineKeyboardButton(text=f"🎵 Приклад {index}", url=url)
        for index, url in enumerate(example_links, start=1)
    ]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="home")])
    await safe_edit(
        callback.message,
        "🎧 Оберіть приклад персональної пісні:",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "contact")
async def contact(callback: CallbackQuery) -> None:
    await safe_edit(
        callback.message,
        "Напишіть своє запитання в цьому чаті — автор відповість вам особисто.",
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "my_orders")
async def my_orders(callback: CallbackQuery) -> None:
    with db() as connection:
        rows = connection.execute(
            "SELECT id, status, created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5",
            (callback.from_user.id,),
        ).fetchall()
    if not rows:
        text = "У вас поки немає оплачених замовлень."
    else:
        text = "Ваші останні замовлення:\n" + "\n".join(
            f"№{row[0]} — {row[1]} — {row[2][:10]}" for row in rows
        )
    await safe_edit(
        callback.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]]),
    )
    await callback.answer()


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>", parse_mode=ParseMode.HTML)


@router.message(Command("paysupport"))
async def pay_support(message: Message) -> None:
    await message.answer("З питань оплати напишіть повідомлення в цьому чаті із номером замовлення.")


@router.message(Command("deliver"))
async def deliver(message: Message) -> None:
    if not ADMIN_CHAT_ID or message.from_user.id != ADMIN_CHAT_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit() or not message.reply_to_message:
        await message.answer("Відповідайте командою /deliver USER_ID на повідомлення з готовим MP3.")
        return
    user_id = int(parts[1])
    await bot.copy_message(user_id, message.chat.id, message.reply_to_message.message_id)
    await bot.send_message(user_id, "Ваша персональна пісня готова ❤️")
    await message.answer("Пісню доставлено клієнту ✅")


@router.message()
async def fallback(message: Message) -> None:
    if ADMIN_CHAT_ID:
        await bot.forward_message(ADMIN_CHAT_ID, message.chat.id, message.message_id)
    await message.answer("Дякую! Повідомлення передано автору.", reply_markup=main_menu())


@asynccontextmanager
async def lifespan(_: FastAPI):
    with db():
        pass
    await bot.set_my_commands([
        BotCommand(command="start", description="Головне меню"),
        BotCommand(command="myid", description="Дізнатися мій Telegram ID"),
        BotCommand(command="paysupport", description="Підтримка з питань оплати"),
    ])
    if WEBHOOK_BASE_URL:
        await bot.set_webhook(
            f"{WEBHOOK_BASE_URL}/webhook",
            secret_token=WEBHOOK_SECRET,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
        log.info("Webhook configured")
    else:
        log.warning("WEBHOOK_BASE_URL/RENDER_EXTERNAL_URL is not set")
    yield
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def health() -> dict:
    return {"status": "ok", "bot": "pisnya-pro-tebe"}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    update = await request.json()
    from aiogram.types import Update

    await dp.feed_update(bot, Update.model_validate(update))
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

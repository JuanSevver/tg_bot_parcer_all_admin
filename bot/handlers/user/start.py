from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.states import UserSG
from bot.keyboards.user_kb import main_menu_kb, instruction_kb, back_to_main_kb
from config import load_config
from database.models import User, Subscription

router = Router(name="start")
_config = load_config()


INSTRUCTION_TEXT = (
    "📘 <b>Инструкция по работе с ботом</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━\n\n"

    "1️⃣  <b>Добавьте прокси (HTTP/SOCKS5)</b>\n"
    "Для возможности добавить аккаунт сначала укажите прокси.\n"
    "Перейдите в раздел «Прокси» → добавьте прокси в формате:\n"
    "<code>ip:порт:логин:пароль</code>\n"
    "Без рабочих прокси аккаунт не подключится.\n\n"

    "2️⃣  <b>Добавьте аккаунт Telegram</b>\n"
    "После настройки прокси перейдите в раздел «Аккаунты» → «Добавить аккаунт».\n"
    "Введите номер телефона и код подтверждения.\n"
    "Этот аккаунт будет собирать сообщения по ключевым словам из групп, "
    "в которых он состоит.\n\n"

    "3️⃣  <b>Добавьте группы (вкладка «Группы»)</b>\n"
    "• «Группы» → «Добавить группу»\n"
    "• Важно: группа должна быть <b>открытой</b>, чтобы бот мог парсить сообщения.\n"
    "• Если группа закрытая (приватная), просто вступите в неё с того аккаунта, "
    "который вы добавили в бота. После этого бот сможет её видеть.\n\n"

    "4️⃣  <b>Настройте категории и ключевые слова</b>\n"
    "В разделе «Категории» создайте категорию, а внутри неё укажите:\n"
    "• 🔑 <b>Ключевые слова</b> — по ним бот будет отбирать сообщения\n"
    "• 🚫 <b>Минус-слова</b> — если они есть в сообщении, оно не попадёт в результат\n\n"
    "<b>Пример:</b>\n"
    "🔑 Ключевые: куплю, продам, цена\n"
    "🚫 Минус-слова: спам, реклама\n\n"
    "После этого бот начнёт присылать подходящие сообщения в реальном времени.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠ <b>Если сообщения не поступают</b>\n\n"
    "1. <b>Включены ли аккаунты и категории?</b>\n"
    "   Зайдите в «Аккаунты» и «Категории» → убедитесь, что напротив каждого "
    "стоит статус «Активен» (зелёный переключатель).\n\n"
    "2. <b>Аккаунт в спам-блоке?</b>\n"
    "   Если аккаунт не может перейти по ссылке или вступить в группу — возможно, "
    "он попал в спам-блок Telegram. Временно замените аккаунт или разблокируйте его.\n\n"
    "3. <b>Группа открыта / аккаунт в ней?</b>\n"
    "   Проверьте, что группа либо открытая, либо аккаунт добавлен в неё как участник.\n\n"
    "4. <b>Нет подходящих сообщений.</b>\n"
    "   Возможно, за указанное время просто не появилось сообщений с вашими "
    "ключевыми словами.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━\n"
    "❓ <b>Частые вопросы</b>\n\n"
    "<b>Как понять, что бот работает?</b>\n"
    "При появлении сообщения по вашему ключевому слову вы увидите его в чате.\n\n"
    "<b>Можно добавить несколько аккаунтов?</b>\n"
    "Да, для каждого нужен отдельный прокси.\n\n"
    "<b>Что делать, если бот не парсит старые сообщения?</b>\n"
    "Бот собирает только новые сообщения после настройки. Старые не парсятся."
)


WELCOME_TEXT = (
    "👋 <b>Добро пожаловать!</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━\n\n"
    "🎁 Вам активирована <b>пробная подписка на 3 дня</b>.\n\n"
    "Чтобы начать получать сообщения, настройте бот по инструкции ниже."
)


async def _get_or_create_user(session: AsyncSession, tg_user) -> tuple[User, bool]:
    """Возвращает (user, is_new). is_new=True только при самом первом /start."""
    result = await session.execute(
        select(User).where(User.id == tg_user.id).options(selectinload(User.subscription))
    )
    user = result.scalar_one_or_none()
    is_new = user is None
    if is_new:
        user = User(
            id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name or tg_user.first_name or "",
            receiving_enabled=True,
        )
        session.add(user)
        await session.flush()
        has_sub = False
    else:
        # selectinload загрузил subscription заранее — обращение к нему безопасно
        # в async. Для НОВОГО пользователя relationship не была eager-loaded,
        # и lazy-load в async-сессии падает MissingGreenlet'ом.
        has_sub = user.subscription is not None

    if not user.trial_used and not has_sub:
        sub = Subscription(
            user_id=user.id,
            plan="trial",
            expires_at=datetime.utcnow() + timedelta(days=3),
            purchases_count=0,
        )
        session.add(sub)
        user.trial_used = True
    await session.commit()
    # Перезагружаем subscription явным запросом — refresh с attribute names
    # тоже может вызвать lazy-load для свежесозданного объекта.
    result = await session.execute(
        select(User).where(User.id == user.id).options(selectinload(User.subscription))
    )
    return result.scalar_one(), is_new


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user, is_new = await _get_or_create_user(session, message.from_user)
    if user.is_blocked:
        await message.answer("🚫 Ваш аккаунт заблокирован. Обратитесь в поддержку.")
        return
    await state.set_state(UserSG.main_menu)
    if is_new:
        await message.answer(WELCOME_TEXT, parse_mode="HTML")
    await message.answer(INSTRUCTION_TEXT, reply_markup=instruction_kb(), parse_mode="HTML")
    # Дашборд отрисует основное меню — отдельный модуль.
    from bot.handlers.user.dashboard import send_dashboard
    await send_dashboard(message, session, user)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(INSTRUCTION_TEXT, reply_markup=instruction_kb(), parse_mode="HTML")


@router.callback_query(F.data == "instruction")
async def cb_instruction(callback: CallbackQuery) -> None:
    await callback.message.edit_text(INSTRUCTION_TEXT, reply_markup=instruction_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    result = await session.execute(
        select(User).where(User.id == callback.from_user.id).options(selectinload(User.subscription))
    )
    user = result.scalar_one_or_none()
    if not user:
        await callback.answer()
        return
    await state.set_state(UserSG.main_menu)
    from bot.handlers.user.dashboard import send_dashboard
    await send_dashboard(callback, session, user)
    await callback.answer()


@router.callback_query(F.data == "toggle_receive")
async def cb_toggle_receive(callback: CallbackQuery, session: AsyncSession) -> None:
    result = await session.execute(
        select(User).where(User.id == callback.from_user.id).options(selectinload(User.subscription))
    )
    user = result.scalar_one_or_none()
    if not user:
        await callback.answer()
        return
    sub = user.subscription
    if not sub or not sub.is_active:
        await callback.answer("❌ У вас нет активной подписки!", show_alert=True)
        return
    user.receiving_enabled = not user.receiving_enabled
    await session.commit()
    status = "включена ✅" if user.receiving_enabled else "отключена 🔴"
    await callback.answer(f"Лента запросов {status}", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=main_menu_kb(user.receiving_enabled))

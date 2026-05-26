from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import proxies_list_kb, cancel_kb
from bot.states import UserProxySG
from database.models import Proxy

router = Router(name="user_proxies")


async def _show_list(target, session: AsyncSession, user_id: int) -> None:
    r = await session.execute(
        select(Proxy).where(Proxy.owner_id == user_id).order_by(Proxy.id)
    )
    proxies = list(r.scalars().all())
    text = (
        f"🛡 <b>Прокси</b> ({len(proxies)})\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Используются для подключения ваших Telegram-аккаунтов."
    )
    kb = proxies_list_kb(proxies)
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await target.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "u:proxies")
async def cb_proxies(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.set_state(UserProxySG.list)
    await _show_list(callback, session, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "u:proxy:add")
async def cb_proxy_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserProxySG.add)
    await callback.message.edit_text(
        "Введите прокси в формате:\n\n"
        "<code>ip:порт:логин:пароль</code>\n\n"
        "или без авторизации:\n"
        "<code>ip:порт</code>\n\n"
        "По умолчанию тип — <b>SOCKS5</b>. Чтобы указать HTTP, добавьте префикс:\n"
        "<code>http:ip:порт:логин:пароль</code>",
        reply_markup=cancel_kb("u:proxies"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(UserProxySG.add)
async def process_proxy_add(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip()
    ptype = "socks5"
    if raw.lower().startswith(("http:", "socks5:")):
        ptype, _, raw = raw.partition(":")
        ptype = ptype.lower()
    parts = raw.split(":")
    if len(parts) not in (2, 4):
        await message.answer(
            "❌ Неверный формат. Примеры:\n"
            "<code>1.2.3.4:1080:user:pass</code>\n"
            "<code>1.2.3.4:1080</code>",
            reply_markup=cancel_kb("u:proxies"),
            parse_mode="HTML",
        )
        return
    host = parts[0]
    try:
        port = int(parts[1])
    except ValueError:
        await message.answer("❌ Порт должен быть числом.", reply_markup=cancel_kb("u:proxies"))
        return
    username = parts[2] if len(parts) == 4 else None
    password = parts[3] if len(parts) == 4 else None
    p = Proxy(
        owner_id=message.from_user.id,
        host=host, port=port,
        username=username, password=password,
        type=ptype,
    )
    session.add(p)
    await session.commit()
    await message.answer(f"✅ Прокси {host}:{port} добавлен.")
    await state.set_state(UserProxySG.list)
    await _show_list(message, session, message.from_user.id)


@router.callback_query(F.data.startswith("u:proxy:delete:"))
async def cb_proxy_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    proxy_id = int(callback.data.split(":")[-1])
    r = await session.execute(
        select(Proxy).where(Proxy.id == proxy_id, Proxy.owner_id == callback.from_user.id)
    )
    p = r.scalar_one_or_none()
    if p:
        await session.delete(p)
        await session.commit()
        await callback.answer("Удалено.", show_alert=False)
    await _show_list(callback, session, callback.from_user.id)


@router.callback_query(F.data.startswith("u:proxy:check:"))
async def cb_proxy_check(callback: CallbackQuery) -> None:
    # Проверка прокси требует поднятого Telethon-клиента; делается при добавлении аккаунта.
    await callback.answer(
        "Прокси будет проверен при привязке к аккаунту.",
        show_alert=True,
    )

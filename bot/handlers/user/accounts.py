from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import accounts_list_kb, account_detail_kb, cancel_kb
from bot.states import UserAccountSG
from database.models import ParserAccount, Proxy
from parser.client import proxy_tuple
from parser.manager import parser_manager, cancel_pending_signin

router = Router(name="user_accounts")
logger = logging.getLogger(__name__)


async def _pick_user_proxy(session: AsyncSession, user_id: int) -> Proxy | None:
    """Берёт первый активный прокси юзера. Если прокси нет — None."""
    r = await session.execute(
        select(Proxy).where(Proxy.owner_id == user_id, Proxy.is_active.is_(True)).order_by(Proxy.id)
    )
    return r.scalars().first()


async def _show_list(target, session: AsyncSession, user_id: int) -> None:
    r = await session.execute(
        select(ParserAccount).where(ParserAccount.owner_id == user_id).order_by(ParserAccount.id)
    )
    accounts = list(r.scalars().all())
    text = (
        f"🤖 <b>Аккаунты</b> ({len(accounts)})\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Telegram-аккаунты, через которые бот собирает сообщения."
    )
    kb = accounts_list_kb(accounts)
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await target.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "u:accounts")
async def cb_accounts(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.set_state(UserAccountSG.list)
    await _show_list(callback, session, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "u:acc:add")
async def cb_acc_add(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    proxy = await _pick_user_proxy(session, callback.from_user.id)
    if not proxy:
        await callback.answer(
            "❌ Сначала добавьте прокси в разделе «Прокси».", show_alert=True,
        )
        return
    await state.update_data(proxy_id=proxy.id)
    await state.set_state(UserAccountSG.add_phone)
    await callback.message.edit_text(
        f"Используется прокси: <code>{proxy.host}:{proxy.port}</code>\n\n"
        "Введите номер телефона в формате <code>+79001234567</code>:",
        reply_markup=cancel_kb("u:accounts"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(UserAccountSG.add_phone)
async def process_phone(message: Message, state: FSMContext, session: AsyncSession) -> None:
    phone = (message.text or "").strip()
    data = await state.get_data()
    proxy_id = data.get("proxy_id")
    proxy_obj = await session.get(Proxy, proxy_id) if proxy_id else None
    if not proxy_obj:
        await state.clear()
        await message.answer("❌ Прокси недоступен.", reply_markup=cancel_kb("u:accounts"))
        return
    px = proxy_tuple(
        proxy_obj.host, proxy_obj.port, proxy_obj.type,
        proxy_obj.username, proxy_obj.password,
    )
    await state.update_data(phone=phone)
    try:
        code_hash = await parser_manager.request_code(phone, proxy=px)
        await state.update_data(phone_code_hash=code_hash)
        await state.set_state(UserAccountSG.add_code)
        await message.answer(
            f"📨 Код отправлен на <code>{phone}</code>. Введите код:",
            reply_markup=cancel_kb("u:accounts"),
            parse_mode="HTML",
        )
    except Exception as e:
        await state.clear()
        logger.exception("user request_code failed")
        await message.answer(
            f"❌ Ошибка отправки кода: {type(e).__name__}",
            reply_markup=cancel_kb("u:accounts"),
        )


@router.message(UserAccountSG.add_code)
async def process_code(message: Message, state: FSMContext, session: AsyncSession) -> None:
    code = (message.text or "").strip()
    data = await state.get_data()
    phone = data["phone"]
    phone_code_hash = data.get("phone_code_hash")
    proxy_id = data.get("proxy_id")
    try:
        session_string = await parser_manager.sign_in(phone, code, phone_code_hash)
        await _save_account(session, message.from_user.id, phone, session_string, proxy_id)
        await message.answer("✅ Аккаунт успешно добавлен!")
        await state.set_state(UserAccountSG.list)
        await _show_list(message, session, message.from_user.id)
    except Exception as e:
        err = str(e).lower()
        if "two" in err or "password" in err or "2fa" in err:
            await state.set_state(UserAccountSG.add_2fa)
            await message.answer(
                "🔒 Требуется пароль 2FA. Введите пароль:",
                reply_markup=cancel_kb("u:accounts"),
            )
        else:
            await state.clear()
            logger.exception("user sign_in failed")
            await message.answer(
                f"❌ Ошибка авторизации: {type(e).__name__}",
                reply_markup=cancel_kb("u:accounts"),
            )


@router.message(UserAccountSG.add_2fa)
async def process_2fa(message: Message, state: FSMContext, session: AsyncSession) -> None:
    password = (message.text or "").strip()
    data = await state.get_data()
    phone = data["phone"]
    proxy_id = data.get("proxy_id")
    try:
        session_string = await parser_manager.sign_in_2fa(phone, password)
        await _save_account(session, message.from_user.id, phone, session_string, proxy_id)
        await message.answer("✅ Аккаунт добавлен (2FA).")
        await state.set_state(UserAccountSG.list)
        await _show_list(message, session, message.from_user.id)
    except Exception as e:
        await state.clear()
        logger.exception("user sign_in_2fa failed")
        await message.answer(
            f"❌ Ошибка 2FA: {type(e).__name__}",
            reply_markup=cancel_kb("u:accounts"),
        )


async def _save_account(
    session: AsyncSession, owner_id: int, phone: str | None,
    session_string: str, proxy_id: int | None,
) -> None:
    acc = ParserAccount(
        owner_id=owner_id,
        phone=phone,
        session_string=session_string,
        proxy_id=proxy_id,
    )
    session.add(acc)
    await session.commit()
    try:
        await parser_manager.reload_clients()
    except Exception:
        logger.exception("reload_clients failed after add")


async def _get_user_acc(session: AsyncSession, user_id: int, acc_id: int) -> ParserAccount | None:
    r = await session.execute(
        select(ParserAccount).where(
            ParserAccount.id == acc_id, ParserAccount.owner_id == user_id
        )
    )
    return r.scalar_one_or_none()


@router.callback_query(F.data.startswith("u:acc:detail:"))
async def cb_acc_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    acc_id = int(callback.data.split(":")[-1])
    acc = await _get_user_acc(session, callback.from_user.id, acc_id)
    if not acc:
        await callback.answer("Аккаунт не найден.", show_alert=True)
        return
    status = "🟢 активен" if acc.is_active and acc.is_valid else "🔴 неактивен/невалиден"
    label = acc.phone or f"ID {acc.id}"
    joined = "ВКЛ ✅" if acc.parse_joined_groups else "ВЫКЛ ❌"
    text = (
        f"🤖 <b>Аккаунт {label}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Статус: {status}\n"
        f"📨 Спарсено сообщений: <b>{acc.messages_parsed}</b>\n"
        f"📂 Парсинг собственных групп: <b>{joined}</b>\n\n"
        "<i>Если включено — аккаунт сканирует все группы, в которых состоит, "
        "а не только добавленные через «Группы».</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=account_detail_kb(acc.id, acc.parse_joined_groups),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("u:acc:toggle_joined:"))
async def cb_acc_toggle_joined(callback: CallbackQuery, session: AsyncSession) -> None:
    acc_id = int(callback.data.split(":")[-1])
    acc = await _get_user_acc(session, callback.from_user.id, acc_id)
    if not acc:
        await callback.answer()
        return
    acc.parse_joined_groups = not acc.parse_joined_groups
    await session.commit()
    try:
        await parser_manager.reload_clients()
    except Exception:
        pass
    # cb_acc_detail сам ответит на callback.
    await cb_acc_detail(callback, session)


@router.callback_query(F.data.startswith("u:acc:reissue:"))
async def cb_acc_reissue(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    acc_id = int(callback.data.split(":")[-1])
    acc = await _get_user_acc(session, callback.from_user.id, acc_id)
    if not acc:
        await callback.answer()
        return
    proxy = await _pick_user_proxy(session, callback.from_user.id)
    if not proxy:
        await callback.answer("Нужен активный прокси.", show_alert=True)
        return
    await state.update_data(proxy_id=proxy.id, reissue_acc_id=acc.id)
    await state.set_state(UserAccountSG.add_phone)
    await callback.message.edit_text(
        f"🔄 Перевыдача сессии для <code>{acc.phone or acc.id}</code>.\n"
        "Введите номер телефона (можно тот же):",
        reply_markup=cancel_kb("u:accounts"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("u:acc:delete:"))
async def cb_acc_delete(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    acc_id = int(callback.data.split(":")[-1])
    acc = await _get_user_acc(session, callback.from_user.id, acc_id)
    if acc:
        await session.delete(acc)
        await session.commit()
        try:
            await parser_manager.reload_clients()
        except Exception:
            pass
        await callback.answer("Удалено.", show_alert=False)
    else:
        await callback.answer()
    await state.set_state(UserAccountSG.list)
    await _show_list(callback, session, callback.from_user.id)

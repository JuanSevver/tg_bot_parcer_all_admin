from __future__ import annotations

from datetime import date

from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import main_menu_kb
from database.models import User, ParserAccount


PLAN_LABELS = {
    "trial": "Пробный",
    "1m": "1 месяц",
    "3m": "3 месяца",
    "1y": "1 год",
}


async def _reset_daily_counter_if_needed(session: AsyncSession, user: User) -> None:
    today = date.today()
    if user.messages_today_date != today:
        user.messages_today = 0
        user.messages_today_date = today
        await session.commit()


def _format_date(dt) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y")


def _format_datetime(dt) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


async def render_dashboard(session: AsyncSession, user: User) -> str:
    await _reset_daily_counter_if_needed(session, user)

    alive_expr = case(
        (and_(ParserAccount.is_active.is_(True), ParserAccount.is_valid.is_(True)), 1),
        else_=0,
    )
    accounts_q = await session.execute(
        select(
            func.count(ParserAccount.id).label("total"),
            func.coalesce(func.sum(alive_expr), 0).label("alive"),
        ).where(ParserAccount.owner_id == user.id)
    )
    row = accounts_q.one()
    total = int(row.total or 0)
    alive = int(row.alive or 0)
    dead = max(0, total - alive)

    sub = user.subscription
    if sub and sub.is_active:
        plan_label = PLAN_LABELS.get(sub.plan, sub.plan)
        sub_line = f"<b>{plan_label}</b> · осталось <b>{sub.days_left} дн.</b>"
    else:
        sub_line = "<i>Нет активной подписки</i>"

    receiving = "🟢 Включена" if user.receiving_enabled else "🔴 Выключена"

    return (
        "🏠 <b>Главное меню</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>Дашборд</b>\n"
        f"  ├ Сегодня: <b>{user.messages_today}</b> запросов\n"
        f"  ├ Всего: <b>{user.messages_received}</b> запросов\n"
        f"  ├ Аккаунты: <b>{alive}</b> в работе · <b>{dead}</b> мертвых\n"
        f"  ├ Подписка: {sub_line}\n"
        f"  └ Регистрация: <b>{_format_date(user.created_at)}</b>\n\n"
        f"📡 Лента: {receiving}"
    )


async def send_dashboard(target: Message | CallbackQuery, session: AsyncSession, user: User) -> None:
    text = await render_dashboard(session, user)
    kb = main_menu_kb(user.receiving_enabled)
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await target.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")

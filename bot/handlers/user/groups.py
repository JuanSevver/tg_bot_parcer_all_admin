from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import (
    groups_list_kb, group_detail_kb, group_categories_kb, cancel_kb,
)
from bot.states import UserGroupSG
from database.models import TelegramGroup, GroupCategory, Category

router = Router(name="user_groups")


def _normalize_link(link: str) -> str:
    link = link.strip()
    for prefix in ("https://", "http://"):
        if link.startswith(prefix):
            link = link[len(prefix):]
            break
    if link.startswith("@"):
        link = "t.me/" + link[1:]
    if not link.startswith("t.me/"):
        link = "t.me/" + link
    return link.lower().rstrip("/")


async def _show_list(target, session: AsyncSession, user_id: int) -> None:
    r = await session.execute(
        select(TelegramGroup).where(TelegramGroup.owner_id == user_id).order_by(TelegramGroup.id)
    )
    groups = list(r.scalars().all())
    text = (
        f"🔗 <b>Группы</b> ({len(groups)})\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Группы и каналы, из которых парсятся сообщения."
    )
    kb = groups_list_kb(groups)
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await target.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "u:groups")
async def cb_groups(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.set_state(UserGroupSG.list)
    await _show_list(callback, session, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "u:grp:add")
async def cb_grp_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserGroupSG.add_link)
    await callback.message.edit_text(
        "Введите ссылку на группу или канал:\n\n"
        "<code>https://t.me/group_name</code>\n"
        "или\n"
        "<code>@group_name</code>\n\n"
        "⚠ Группа должна быть открытой, либо ваш аккаунт уже в ней состоит.",
        reply_markup=cancel_kb("u:groups"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(UserGroupSG.add_link)
async def process_grp_add(message: Message, state: FSMContext, session: AsyncSession) -> None:
    link = _normalize_link(message.text or "")
    if "/" not in link or len(link) < 6:
        await message.answer("❌ Неверная ссылка.", reply_markup=cancel_kb("u:groups"))
        return
    g = TelegramGroup(owner_id=message.from_user.id, link=link, is_active=True)
    session.add(g)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await message.answer("Эта группа уже добавлена.", reply_markup=cancel_kb("u:groups"))
        return
    await message.answer(f"✅ Группа добавлена: <code>{link}</code>", parse_mode="HTML")
    await state.set_state(UserGroupSG.list)
    await _show_list(message, session, message.from_user.id)


async def _get_user_group(session: AsyncSession, user_id: int, group_id: int) -> TelegramGroup | None:
    r = await session.execute(
        select(TelegramGroup).where(
            TelegramGroup.id == group_id, TelegramGroup.owner_id == user_id
        )
    )
    return r.scalar_one_or_none()


@router.callback_query(F.data.startswith("u:grp:detail:"))
async def cb_grp_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    gid = int(callback.data.split(":")[-1])
    g = await _get_user_group(session, callback.from_user.id, gid)
    if not g:
        await callback.answer("Группа не найдена.", show_alert=True)
        return
    cr = await session.execute(
        select(GroupCategory).where(GroupCategory.group_id == gid)
    )
    assigned_count = len(cr.scalars().all())
    status = "🟢 активна" if g.is_active else "🔴 отключена"
    text = (
        f"🔗 <b>{g.title or g.link}</b> — {status}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ссылка: <code>{g.link}</code>\n"
        f"Привязано категорий: <b>{assigned_count if assigned_count else 'все'}</b>"
    )
    await callback.message.edit_text(
        text, reply_markup=group_detail_kb(g, assigned_count), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("u:grp:toggle:"))
async def cb_grp_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    gid = int(callback.data.split(":")[-1])
    g = await _get_user_group(session, callback.from_user.id, gid)
    if not g:
        await callback.answer()
        return
    g.is_active = not g.is_active
    await session.commit()
    # cb_grp_detail сам ответит на callback.
    await cb_grp_detail(callback, session)


@router.callback_query(F.data.startswith("u:grp:delete:"))
async def cb_grp_delete(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    gid = int(callback.data.split(":")[-1])
    g = await _get_user_group(session, callback.from_user.id, gid)
    if g:
        await session.delete(g)
        await session.commit()
        await callback.answer("Группа удалена.", show_alert=False)
    else:
        await callback.answer()
    await state.set_state(UserGroupSG.list)
    await _show_list(callback, session, callback.from_user.id)


@router.callback_query(F.data.startswith("u:grp:cats:"))
async def cb_grp_cats(callback: CallbackQuery, session: AsyncSession) -> None:
    gid = int(callback.data.split(":")[-1])
    g = await _get_user_group(session, callback.from_user.id, gid)
    if not g:
        await callback.answer()
        return
    cr = await session.execute(
        select(Category).where(Category.owner_id == callback.from_user.id).order_by(Category.id)
    )
    cats = list(cr.scalars().all())
    ar = await session.execute(
        select(GroupCategory).where(GroupCategory.group_id == gid)
    )
    assigned = {gc.category_id for gc in ar.scalars().all()}
    text = (
        f"📂 <b>Категории для «{g.title or g.link}»</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Если ни одна не выбрана — группа парсится для всех ваших категорий."
    )
    await callback.message.edit_text(
        text, reply_markup=group_categories_kb(gid, cats, assigned), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("u:grp:cat_toggle:"))
async def cb_grp_cat_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    gid, cat_id = int(parts[-2]), int(parts[-1])
    g = await _get_user_group(session, callback.from_user.id, gid)
    if not g:
        await callback.answer()
        return
    cr = await session.execute(
        select(Category).where(
            Category.id == cat_id, Category.owner_id == callback.from_user.id
        )
    )
    if not cr.scalar_one_or_none():
        await callback.answer()
        return
    er = await session.execute(
        select(GroupCategory).where(
            GroupCategory.group_id == gid, GroupCategory.category_id == cat_id
        )
    )
    gc = er.scalar_one_or_none()
    if gc:
        await session.delete(gc)
    else:
        session.add(GroupCategory(group_id=gid, category_id=cat_id))
    await session.commit()
    await cb_grp_cats(callback, session)

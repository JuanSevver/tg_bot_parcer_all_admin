from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import (
    categories_list_kb, category_detail_kb, category_accounts_kb, cancel_kb,
)
from bot.states import UserCategorySG
from database.models import Category, CategoryAccount, ParserAccount

router = Router(name="user_categories")


def _cat_detail_text(cat: Category) -> str:
    kws = cat.get_keywords()
    sws = cat.get_stop_words()
    kw_text = "\n".join(f"  • {k}" for k in kws) if kws else "  <i>нет</i>"
    sw_text = "\n".join(f"  • {w}" for w in sws) if sws else "  <i>нет</i>"
    status = "🟢 активна" if cat.is_active else "🔴 отключена"
    return (
        f"📂 <b>{cat.name}</b> — {status}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 <b>Ключевые фразы</b> <i>(любая одна)</i>:\n{kw_text}\n\n"
        f"🚫 <b>Минус-слова</b> <i>(блокируют пост)</i>:\n{sw_text}"
    )


async def _get_user_cat(session: AsyncSession, user_id: int, cat_id: int) -> Category | None:
    r = await session.execute(
        select(Category).where(Category.id == cat_id, Category.owner_id == user_id)
    )
    return r.scalar_one_or_none()


async def _show_list(callback_or_msg, session: AsyncSession, user_id: int) -> None:
    r = await session.execute(
        select(Category).where(Category.owner_id == user_id).order_by(Category.id)
    )
    cats = list(r.scalars().all())
    text = f"📂 <b>Категории</b> ({len(cats)})"
    kb = categories_list_kb(cats)
    if isinstance(callback_or_msg, CallbackQuery):
        try:
            await callback_or_msg.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback_or_msg.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await callback_or_msg.answer(text, reply_markup=kb, parse_mode="HTML")


async def _show_detail(callback: CallbackQuery, state: FSMContext, cat: Category) -> None:
    await state.update_data(current_cat_id=cat.id)
    await state.set_state(UserCategorySG.detail)
    try:
        await callback.message.edit_text(
            _cat_detail_text(cat),
            reply_markup=category_detail_kb(cat.id),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            _cat_detail_text(cat),
            reply_markup=category_detail_kb(cat.id),
            parse_mode="HTML",
        )


async def _reply_and_show_detail(
    message: Message, state: FSMContext, session: AsyncSession, text: str
) -> None:
    data = await state.get_data()
    cat_id = data["current_cat_id"]
    cat = await _get_user_cat(session, message.from_user.id, cat_id)
    if not cat:
        await message.answer("Категория не найдена.")
        return
    await message.answer(text, parse_mode="HTML")
    await message.answer(
        _cat_detail_text(cat),
        reply_markup=category_detail_kb(cat_id),
        parse_mode="HTML",
    )
    await state.set_state(UserCategorySG.detail)


@router.callback_query(F.data == "u:categories")
async def cb_categories(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.set_state(UserCategorySG.list)
    await _show_list(callback, session, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "u:cat:create")
async def cb_cat_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserCategorySG.create_name)
    await callback.message.edit_text(
        "Введите название новой категории:",
        reply_markup=cancel_kb("u:categories"),
    )
    await callback.answer()


@router.message(UserCategorySG.create_name)
async def process_cat_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Пустое название. Введите ещё раз:")
        return
    cat = Category(owner_id=message.from_user.id, name=name)
    session.add(cat)
    await session.commit()
    await message.answer(f"✅ Категория «{cat.name}» создана.")
    await state.set_state(UserCategorySG.list)
    await _show_list(message, session, message.from_user.id)


@router.callback_query(F.data.startswith("u:cat:detail:"))
async def cb_cat_detail(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[-1])
    cat = await _get_user_cat(session, callback.from_user.id, cat_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    await _show_detail(callback, state, cat)
    await callback.answer()


@router.callback_query(F.data.startswith("u:cat:toggle:"))
async def cb_cat_toggle(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[-1])
    cat = await _get_user_cat(session, callback.from_user.id, cat_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    cat.is_active = not cat.is_active
    await session.commit()
    await _show_detail(callback, state, cat)


@router.callback_query(F.data.startswith("u:cat:addkw:"))
async def cb_cat_addkw(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[-1])
    await state.update_data(current_cat_id=cat_id)
    await state.set_state(UserCategorySG.add_keyword)
    await callback.message.edit_text(
        "Введите ключевые <b>фразы</b> — каждая с новой строки.\n\n"
        "• Одна строка = одна фраза\n"
        "• Слова внутри строки должны быть <b>все вместе</b> в тексте (AND)\n"
        "• Разные строки — это синонимы (OR)\n\n"
        "<i>Пример:</i>\n"
        "<code>куплю iphone</code>\n"
        "<code>продам ноутбук</code>",
        reply_markup=cancel_kb(f"u:cat:detail:{cat_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(UserCategorySG.add_keyword)
async def process_add_kw(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    cat_id = data["current_cat_id"]
    cat = await _get_user_cat(session, message.from_user.id, cat_id)
    if not cat:
        await message.answer("Категория не найдена.")
        return
    new_kws = [k.strip().lower() for k in (message.text or "").splitlines() if k.strip()]
    merged = list(dict.fromkeys(cat.get_keywords() + new_kws))
    cat.set_keywords(merged)
    await session.commit()
    await _reply_and_show_detail(
        message, state, session,
        f"✅ Добавлено фраз: <b>{len(new_kws)}</b>. Всего: <b>{len(merged)}</b>.",
    )


@router.callback_query(F.data.startswith("u:cat:delkw:"))
async def cb_cat_delkw(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[-1])
    cat = await _get_user_cat(session, callback.from_user.id, cat_id)
    if not cat:
        await callback.answer()
        return
    kws = cat.get_keywords()
    if not kws:
        await callback.answer("Ключевых фраз нет.", show_alert=True)
        return
    await state.update_data(current_cat_id=cat_id)
    await state.set_state(UserCategorySG.delete_keyword)
    await callback.message.edit_text(
        "Введите фразу для удаления:\n\n" + "\n".join(f"• {k}" for k in kws),
        reply_markup=cancel_kb(f"u:cat:detail:{cat_id}"),
    )
    await callback.answer()


@router.message(UserCategorySG.delete_keyword)
async def process_del_kw(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    cat_id = data["current_cat_id"]
    cat = await _get_user_cat(session, message.from_user.id, cat_id)
    if not cat:
        await message.answer("Категория не найдена.")
        return
    to_delete = (message.text or "").strip().lower()
    cat.set_keywords([k for k in cat.get_keywords() if k != to_delete])
    await session.commit()
    await _reply_and_show_detail(
        message, state, session, f"✅ Фраза «{to_delete}» удалена.",
    )


@router.callback_query(F.data.startswith("u:cat:addsw:"))
async def cb_cat_addsw(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[-1])
    await state.update_data(current_cat_id=cat_id)
    await state.set_state(UserCategorySG.add_stop_word)
    await callback.message.edit_text(
        "Введите минус-слова — каждое с новой строки или через запятую.\n\n"
        "Посты с этими словами <b>не будут</b> приходить.",
        reply_markup=cancel_kb(f"u:cat:detail:{cat_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(UserCategorySG.add_stop_word)
async def process_add_sw(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    cat_id = data["current_cat_id"]
    cat = await _get_user_cat(session, message.from_user.id, cat_id)
    if not cat:
        await message.answer("Категория не найдена.")
        return
    raw = (message.text or "").replace(",", "\n")
    new_sws = [w.strip().lower() for w in raw.splitlines() if w.strip()]
    merged = list(dict.fromkeys(cat.get_stop_words() + new_sws))
    cat.set_stop_words(merged)
    await session.commit()
    await _reply_and_show_detail(
        message, state, session,
        f"✅ Добавлено минус-слов: <b>{len(new_sws)}</b>. Всего: <b>{len(merged)}</b>.",
    )


@router.callback_query(F.data.startswith("u:cat:delsw:"))
async def cb_cat_delsw(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[-1])
    cat = await _get_user_cat(session, callback.from_user.id, cat_id)
    if not cat:
        await callback.answer()
        return
    sws = cat.get_stop_words()
    if not sws:
        await callback.answer("Минус-слов нет.", show_alert=True)
        return
    await state.update_data(current_cat_id=cat_id)
    await state.set_state(UserCategorySG.delete_stop_word)
    await callback.message.edit_text(
        "Введите минус-слово для удаления:\n\n" + "\n".join(f"• {w}" for w in sws),
        reply_markup=cancel_kb(f"u:cat:detail:{cat_id}"),
    )
    await callback.answer()


@router.message(UserCategorySG.delete_stop_word)
async def process_del_sw(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    cat_id = data["current_cat_id"]
    cat = await _get_user_cat(session, message.from_user.id, cat_id)
    if not cat:
        await message.answer("Категория не найдена.")
        return
    to_delete = (message.text or "").strip().lower()
    cat.set_stop_words([w for w in cat.get_stop_words() if w != to_delete])
    await session.commit()
    await _reply_and_show_detail(
        message, state, session, f"✅ Минус-слово «{to_delete}» удалено.",
    )


@router.callback_query(F.data.startswith("u:cat:delete:"))
async def cb_cat_delete(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[-1])
    cat = await _get_user_cat(session, callback.from_user.id, cat_id)
    if cat:
        await session.delete(cat)
        await session.commit()
        await callback.answer("✅ Категория удалена.", show_alert=True)
    await state.set_state(UserCategorySG.list)
    await _show_list(callback, session, callback.from_user.id)


@router.callback_query(F.data.startswith("u:cat:accounts:"))
async def cb_cat_accounts(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[-1])
    cat = await _get_user_cat(session, callback.from_user.id, cat_id)
    if not cat:
        await callback.answer("Категория не найдена.", show_alert=True)
        return
    r = await session.execute(
        select(ParserAccount)
        .where(ParserAccount.owner_id == callback.from_user.id)
        .order_by(ParserAccount.id)
    )
    accounts = list(r.scalars().all())
    ar = await session.execute(
        select(CategoryAccount).where(CategoryAccount.category_id == cat_id)
    )
    assigned_ids = {ca.account_id for ca in ar.scalars().all()}
    note = "  <i>Ни один не выбран — парсят все ваши аккаунты.</i>" if not assigned_ids else ""
    text = (
        f"🤖 <b>Аккаунты для «{cat.name}»</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Выберите какие аккаунты будут собирать сообщения для этой категории.\n{note}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=category_accounts_kb(cat_id, accounts, assigned_ids),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("u:cat:acc_toggle:"))
async def cb_cat_acc_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    cat_id, acc_id = int(parts[-2]), int(parts[-1])
    # Verify ownership
    cat = await _get_user_cat(session, callback.from_user.id, cat_id)
    if not cat:
        await callback.answer()
        return
    acc_r = await session.execute(
        select(ParserAccount).where(
            ParserAccount.id == acc_id, ParserAccount.owner_id == callback.from_user.id
        )
    )
    if not acc_r.scalar_one_or_none():
        await callback.answer()
        return
    existing = await session.execute(
        select(CategoryAccount).where(
            CategoryAccount.category_id == cat_id, CategoryAccount.account_id == acc_id
        )
    )
    ca = existing.scalar_one_or_none()
    if ca:
        await session.delete(ca)
    else:
        session.add(CategoryAccount(category_id=cat_id, account_id=acc_id))
    await session.commit()
    await callback.answer()
    # Refresh accounts page
    await cb_cat_accounts(callback, session)


@router.callback_query(F.data == "noop")
async def _noop(callback: CallbackQuery) -> None:
    await callback.answer()

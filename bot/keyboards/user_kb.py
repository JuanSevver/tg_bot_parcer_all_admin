from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Category, TelegramGroup, ParserAccount, Proxy
from config import load_config

_config = load_config()


# ─────────────────────────────────────────── main menu / dashboard

def main_menu_kb(receiving_enabled: bool) -> InlineKeyboardMarkup:
    receive_text = "📡 Получать запросы: ВКЛ" if receiving_enabled else "📡 Получать запросы: ВЫКЛ"
    receive_style = "success" if receiving_enabled else "danger"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=receive_text, callback_data="toggle_receive", style=receive_style))
    builder.row(InlineKeyboardButton(text="📂 Категории", callback_data="u:categories", style="primary"))
    builder.row(InlineKeyboardButton(text="🤖 Аккаунты", callback_data="u:accounts", style="primary"))
    builder.row(InlineKeyboardButton(text="🔗 Группы", callback_data="u:groups", style="primary"))
    builder.row(InlineKeyboardButton(text="🛡 Прокси", callback_data="u:proxies", style="primary"))
    builder.row(InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription", style="primary"))
    builder.row(InlineKeyboardButton(text="📋 Инструкция", callback_data="instruction", style="primary"))
    builder.row(InlineKeyboardButton(text="🆘 Поддержка", url=f"https://t.me/{_config.support_username}"))
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="main_menu", style="primary"))
    return builder.as_markup()


def instruction_kb() -> InlineKeyboardMarkup:
    return back_to_main_kb()


# ─────────────────────────────────────────── subscription (purchase)

def subscription_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 1 месяц — 20 USDT", callback_data="plan_1m", style="primary"))
    builder.row(InlineKeyboardButton(text="📅 3 месяца — 45 USDT", callback_data="plan_3m", style="primary"))
    builder.row(InlineKeyboardButton(text="📅 1 год — 200 USDT", callback_data="plan_1y", style="primary"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="main_menu", style="primary"))
    return builder.as_markup()


def payment_kb(plan: str, invoice_url: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if invoice_url:
        builder.row(InlineKeyboardButton(text="💎 Оплатить Crypto USDT", url=invoice_url, style="success"))
    builder.row(InlineKeyboardButton(
        text="🆘 Купить через поддержку",
        url=f"https://t.me/{_config.support_username}",
    ))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="buy_subscription", style="primary"))
    return builder.as_markup()


# ─────────────────────────────────────────── cancel helper

def cancel_kb(callback_data: str, label: str = "◀ Отмена") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=label, callback_data=callback_data, style="primary"))
    return builder.as_markup()


# ─────────────────────────────────────────── categories (user-owned)

def categories_list_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        style = "success" if cat.is_active else "danger"
        status = "ВКЛ" if cat.is_active else "ВЫКЛ"
        builder.row(InlineKeyboardButton(
            text=f"{status}  {cat.name}",
            callback_data=f"u:cat:detail:{cat.id}",
            style=style,
        ))
    builder.row(InlineKeyboardButton(text="➕ Добавить категорию", callback_data="u:cat:create", style="success"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="main_menu", style="primary"))
    return builder.as_markup()


def category_detail_kb(cat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Ключевое слово", callback_data=f"u:cat:addkw:{cat_id}", style="success"))
    builder.row(InlineKeyboardButton(text="➖ Удалить ключевое слово", callback_data=f"u:cat:delkw:{cat_id}", style="danger"))
    builder.row(InlineKeyboardButton(text="🚫 Добавить минус-слово", callback_data=f"u:cat:addsw:{cat_id}", style="primary"))
    builder.row(InlineKeyboardButton(text="✂️ Удалить минус-слово", callback_data=f"u:cat:delsw:{cat_id}", style="danger"))
    builder.row(InlineKeyboardButton(text="🤖 Аккаунты-парсеры", callback_data=f"u:cat:accounts:{cat_id}", style="primary"))
    builder.row(InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data=f"u:cat:toggle:{cat_id}", style="primary"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить категорию", callback_data=f"u:cat:delete:{cat_id}", style="danger"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="u:categories", style="primary"))
    return builder.as_markup()


def category_accounts_kb(cat_id: int, accounts: list[ParserAccount], assigned_ids: set[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not accounts:
        builder.row(InlineKeyboardButton(text="⚠️ Нет аккаунтов", callback_data="noop", style="primary"))
    for acc in accounts:
        label = acc.phone or f"ID {acc.id}"
        is_on = acc.id in assigned_ids
        icon = "✅" if is_on else "☐"
        style = "success" if is_on else "primary"
        builder.row(InlineKeyboardButton(
            text=f"{icon} {label}",
            callback_data=f"u:cat:acc_toggle:{cat_id}:{acc.id}",
            style=style,
        ))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data=f"u:cat:detail:{cat_id}", style="primary"))
    return builder.as_markup()


# ─────────────────────────────────────────── accounts

def accounts_list_kb(accounts: list[ParserAccount]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for acc in accounts:
        style = "success" if acc.is_active and acc.is_valid else "danger"
        label = acc.phone or f"ID {acc.id}"
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=f"u:acc:detail:{acc.id}",
            style=style,
        ))
    builder.row(InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="u:acc:add", style="success"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="main_menu", style="primary"))
    return builder.as_markup()


def account_detail_kb(acc_id: int, parse_joined: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    joined_label = "✅ Парсить свои группы: ВКЛ" if parse_joined else "❌ Парсить свои группы: ВЫКЛ"
    joined_style = "success" if parse_joined else "danger"
    builder.row(InlineKeyboardButton(text=joined_label, callback_data=f"u:acc:toggle_joined:{acc_id}", style=joined_style))
    builder.row(InlineKeyboardButton(text="🔄 Перевыдать сессию", callback_data=f"u:acc:reissue:{acc_id}", style="primary"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data=f"u:acc:delete:{acc_id}", style="danger"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="u:accounts", style="primary"))
    return builder.as_markup()


# ─────────────────────────────────────────── groups

def groups_list_kb(groups: list[TelegramGroup]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for g in groups:
        style = "success" if g.is_active else "danger"
        status = "ВКЛ" if g.is_active else "ВЫКЛ"
        title = g.title or g.link
        builder.row(InlineKeyboardButton(
            text=f"{status}  {title[:35]}",
            callback_data=f"u:grp:detail:{g.id}",
            style=style,
        ))
    builder.row(InlineKeyboardButton(text="➕ Добавить группу", callback_data="u:grp:add", style="success"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="main_menu", style="primary"))
    return builder.as_markup()


def group_detail_kb(group: TelegramGroup, assigned_count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    active_label = "✅ Активна — выключить" if group.is_active else "❌ Выключена — включить"
    active_style = "success" if group.is_active else "danger"
    builder.row(InlineKeyboardButton(text=active_label, callback_data=f"u:grp:toggle:{group.id}", style=active_style))
    cats_label = f"📂 Категории ({assigned_count if assigned_count else 'все'})"
    builder.row(InlineKeyboardButton(text=cats_label, callback_data=f"u:grp:cats:{group.id}", style="primary"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить группу", callback_data=f"u:grp:delete:{group.id}", style="danger"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="u:groups", style="primary"))
    return builder.as_markup()


def group_categories_kb(group_id: int, categories: list[Category], assigned_ids: set[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        is_on = cat.id in assigned_ids
        icon = "✅" if is_on else "☐"
        style = "success" if is_on else "primary"
        builder.row(InlineKeyboardButton(
            text=f"{icon} {cat.name}",
            callback_data=f"u:grp:cat_toggle:{group_id}:{cat.id}",
            style=style,
        ))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data=f"u:grp:detail:{group_id}", style="primary"))
    return builder.as_markup()


# ─────────────────────────────────────────── proxies

def proxies_list_kb(proxies: list[Proxy]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in proxies:
        style = "success" if p.is_working else ("danger" if p.is_working is False else "primary")
        builder.row(
            InlineKeyboardButton(text=f"{p.host}:{p.port}", callback_data=f"u:proxy:check:{p.id}", style=style),
            InlineKeyboardButton(text="🗑", callback_data=f"u:proxy:delete:{p.id}", style="danger"),
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить прокси", callback_data="u:proxy:add", style="success"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="main_menu", style="primary"))
    return builder.as_markup()


# ─────────────────────────────────────────── parsed message delivery

def message_action_kb(author_username: str | None, author_link: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    link = author_link or (f"https://t.me/{author_username}" if author_username else None)
    if link:
        builder.row(InlineKeyboardButton(text="✉ Написать пользователю", url=link, style="primary"))
    return builder.as_markup()

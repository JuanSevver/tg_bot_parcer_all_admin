from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram user id
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(256))
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    receiving_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    messages_received: Mapped[int] = mapped_column(Integer, default=0)
    messages_today: Mapped[int] = mapped_column(Integer, default=0)
    messages_today_date: Mapped[date | None] = mapped_column(Date)

    subscription: Mapped[Subscription | None] = relationship(
        "Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    categories: Mapped[list[Category]] = relationship(
        "Category", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
    accounts: Mapped[list[ParserAccount]] = relationship(
        "ParserAccount", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
    groups: Mapped[list[TelegramGroup]] = relationship(
        "TelegramGroup", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
    proxies: Mapped[list[Proxy]] = relationship(
        "Proxy", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    plan: Mapped[str] = mapped_column(String(16))  # trial / 1m / 3m / 1y
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    purchases_count: Mapped[int] = mapped_column(Integer, default=0)  # paid only, trial excluded

    user: Mapped[User] = relationship("User", back_populates="subscription")

    @property
    def is_active(self) -> bool:
        return self.expires_at > datetime.utcnow()

    @property
    def days_left(self) -> int:
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    keywords: Mapped[str] = mapped_column(Text, default="")   # newline-separated phrases
    stop_words: Mapped[str] = mapped_column(Text, default="") # newline-separated words

    owner: Mapped[User] = relationship("User", back_populates="categories")
    groups: Mapped[list[GroupCategory]] = relationship(
        "GroupCategory", back_populates="category", cascade="all, delete-orphan", passive_deletes=True,
    )
    account_assignments: Mapped[list[CategoryAccount]] = relationship(
        "CategoryAccount", back_populates="category", cascade="all, delete-orphan", passive_deletes=True,
    )

    def get_keywords(self) -> list[str]:
        return [k.strip().lower() for k in (self.keywords or "").splitlines() if k.strip()]

    def set_keywords(self, kws: list[str]) -> None:
        self.keywords = "\n".join(k.strip().lower() for k in kws if k.strip())

    def get_stop_words(self) -> list[str]:
        return [w.strip().lower() for w in (self.stop_words or "").splitlines() if w.strip()]

    def set_stop_words(self, words: list[str]) -> None:
        self.stop_words = "\n".join(w.strip().lower() for w in words if w.strip())


class TelegramGroup(Base):
    __tablename__ = "telegram_groups"
    __table_args__ = (UniqueConstraint("owner_id", "link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    link: Mapped[str] = mapped_column(String(256))
    title: Mapped[str | None] = mapped_column(String(256))
    is_channel: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    owner: Mapped[User] = relationship("User", back_populates="groups")
    categories: Mapped[list[GroupCategory]] = relationship("GroupCategory", back_populates="group")


class GroupCategory(Base):
    __tablename__ = "group_categories"
    __table_args__ = (UniqueConstraint("group_id", "category_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("telegram_groups.id", ondelete="CASCADE"))
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id", ondelete="CASCADE"))

    group: Mapped[TelegramGroup] = relationship("TelegramGroup", back_populates="categories")
    category: Mapped[Category] = relationship("Category", back_populates="groups")


class Proxy(Base):
    __tablename__ = "proxies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    host: Mapped[str] = mapped_column(String(256))
    port: Mapped[int] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(128))
    password: Mapped[str | None] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(16), default="socks5")  # socks5 / http
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_working: Mapped[bool | None] = mapped_column(Boolean)

    owner: Mapped[User] = relationship("User", back_populates="proxies")
    accounts: Mapped[list[ParserAccount]] = relationship("ParserAccount", back_populates="proxy")


class ParserAccount(Base):
    __tablename__ = "parser_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    session_string: Mapped[str | None] = mapped_column(Text)  # Telethon StringSession
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    proxy_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("proxies.id"))
    parse_joined_groups: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    messages_parsed: Mapped[int] = mapped_column(Integer, default=0)

    owner: Mapped[User] = relationship("User", back_populates="accounts")
    proxy: Mapped[Proxy | None] = relationship("Proxy", back_populates="accounts")
    category_assignments: Mapped[list[CategoryAccount]] = relationship(
        "CategoryAccount", back_populates="account", cascade="all, delete-orphan", passive_deletes=True,
    )


class CategoryAccount(Base):
    """Привязка аккаунта к категории. Если для категории нет записей — парсят все аккаунты владельца."""
    __tablename__ = "category_accounts"
    __table_args__ = (UniqueConstraint("category_id", "account_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("parser_accounts.id", ondelete="CASCADE"))

    category: Mapped[Category] = relationship("Category", back_populates="account_assignments")
    account: Mapped[ParserAccount] = relationship("ParserAccount", back_populates="category_assignments")


class ParsedMessage(Base):
    __tablename__ = "parsed_messages"
    __table_args__ = (
        UniqueConstraint("owner_id", "group_id", "message_id"),
        Index("ix_parsed_owner_author_hash_time", "owner_id", "author_id", "text_hash", "parsed_at"),
        Index("ix_parsed_parsed_at", "parsed_at"),
        Index("ix_parsed_owner_parsed_at", "owner_id", "parsed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    author_id: Mapped[int | None] = mapped_column(BigInteger)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id", ondelete="SET NULL"))
    text: Mapped[str | None] = mapped_column(Text)
    text_hash: Mapped[str | None] = mapped_column(String(32))
    author_username: Mapped[str | None] = mapped_column(String(64))
    author_link: Mapped[str | None] = mapped_column(String(256))
    parsed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class ProcessedInvoice(Base):
    __tablename__ = "processed_invoices"

    invoice_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class BroadcastHistory(Base):
    __tablename__ = "broadcast_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(32))
    message_text: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    total: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)

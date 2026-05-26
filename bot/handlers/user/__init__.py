from aiogram import Router

from .start import router as start_router
from .categories import router as categories_router
from .accounts import router as accounts_router
from .groups import router as groups_router
from .proxies import router as proxies_router
from .subscription import router as subscription_router

user_router = Router(name="user")
user_router.include_routers(
    start_router,
    categories_router,
    accounts_router,
    groups_router,
    proxies_router,
    subscription_router,
)

__all__ = ["user_router"]

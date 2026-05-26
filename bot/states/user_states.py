from aiogram.fsm.state import State, StatesGroup


class UserSG(StatesGroup):
    main_menu = State()


class SubscriptionSG(StatesGroup):
    choose_plan = State()
    choose_payment = State()
    waiting_crypto_payment = State()


class UserCategorySG(StatesGroup):
    list = State()
    create_name = State()
    detail = State()
    add_keyword = State()
    delete_keyword = State()
    add_stop_word = State()
    delete_stop_word = State()


class UserAccountSG(StatesGroup):
    list = State()
    add_phone = State()
    add_code = State()
    add_2fa = State()


class UserGroupSG(StatesGroup):
    list = State()
    add_link = State()


class UserProxySG(StatesGroup):
    list = State()
    add = State()

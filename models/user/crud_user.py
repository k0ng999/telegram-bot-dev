from sqlalchemy import select, insert
from sqlalchemy.exc import SQLAlchemyError
from datetime import date
from models.user import user_engine
from models.user.models import sellers


def get_user(telegram_id):
    try:
        with user_engine.connect() as conn:
            query = select(sellers).where(sellers.c.telegram_id == str(telegram_id))
            result = conn.execute(query).fetchone()
            return dict(result._mapping) if result else None
    except SQLAlchemyError as e:
        print("Ошибка при получении продавца:", e)
        return None



def add_user(telegram_id: int, name: str, shop_name: str, city: str):
    try:
        with user_engine.begin() as conn:
            stmt = insert(sellers).values(
                telegram_id=str(telegram_id),
                name=name,
                shop_name=shop_name,
                city=city,
                registration_date=date.today()
            )
            conn.execute(stmt)
    except SQLAlchemyError as e:
        print("Ошибка при добавлении продавца:", e)


def get_all_telegram_ids():
    try:
        with user_engine.connect() as conn:
            query = select(sellers.c.telegram_id)
            results = conn.execute(query).fetchall()
            return [row[0] for row in results]
    except SQLAlchemyError as e:
        print("Ошибка при получении telegram_id:", e)
        return []

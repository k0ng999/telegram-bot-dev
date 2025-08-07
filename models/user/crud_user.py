from sqlalchemy.exc import SQLAlchemyError
from datetime import date
from models.user import SessionLocal
from models.user.models import Seller

def get_user(telegram_id: int):
    try:
        with SessionLocal() as session:
            user = session.query(Seller).filter(Seller.telegram_id == str(telegram_id)).first()
            if user:
                # Преобразуем объект ORM в dict
                return {
                    "id": user.id,
                    "registration_date": user.registration_date,
                    "telegram_id": user.telegram_id,
                    "name": user.name,
                    "shop_name": user.shop_name,
                    "city": user.city,
                    "bank_name": user.bank_name,
                    "card_number": user.card_number,
                }
            return None
    except SQLAlchemyError as e:
        print("Ошибка при получении продавца:", e)
        return None


def add_user(telegram_id: int, username: str, name: str, shop_name: str, city: str):
    try:
        with SessionLocal() as session:
            new_seller = Seller(
                telegram_id=str(telegram_id),
                name=name,
                shop_name=shop_name,
                city=city,
                registration_date=date.today(),
                username=username
            )
            session.add(new_seller)
            session.commit()
    except SQLAlchemyError as e:
        print("Ошибка при добавлении продавца:", e)


def get_all_telegram_ids():
    try:
        with SessionLocal() as session:
            telegram_ids = session.query(Seller.telegram_id).all()
            return [tid[0] for tid in telegram_ids]
    except SQLAlchemyError as e:
        print("Ошибка при получении telegram_id:", e)
        return []

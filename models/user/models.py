from sqlalchemy import (
    Table, Column, String, Integer, Date, Boolean, ForeignKey, MetaData
)
import sqlalchemy.dialects.postgresql as pg

metadata = MetaData()

# sellers — Продавцы
sellers = Table(
    "sellers",
    metadata,
    Column("id", pg.UUID(as_uuid=True), primary_key=True),
    Column("registration_date", Date, nullable=False),
    Column("telegram_id", String, unique=True, nullable=False),
    Column("name", String, nullable=False),
    Column("shop_name", String, nullable=False),
    Column("city", String, nullable=False),
    Column("bank_name", String),
    Column("card_number", String),
)

# exams — Экзамены продавца
exams = Table(
    "exams",
    metadata,
    Column("id", pg.UUID(as_uuid=True), primary_key=True),
    Column("seller_id", pg.UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False),
    Column("exam_date", Date, nullable=False),
    Column("correct_answers", Integer, nullable=False),
)

# shipments — Отгрузки товаров
shipments = Table(
    "shipments",
    metadata,
    Column("id", pg.UUID(as_uuid=True), primary_key=True),
    Column("seller_id", pg.UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False),
    Column("shipment_date", Date, nullable=False),
    Column("shipped_quantity", Integer, nullable=False),
)

# sales_reports — Отчёты о продажах
sales_reports = Table(
    "sales_reports",
    metadata,
    Column("id", pg.UUID(as_uuid=True), primary_key=True),
    Column("seller_id", pg.UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False),
    Column("report_date", Date, nullable=False),
    Column("sold_quantity", Integer, nullable=False),
    Column("receipt_photo_url", String),
    Column("moderation_passed", Boolean),
)

# layouts — Фото выкладки товара
layouts = Table(
    "layouts",
    metadata,
    Column("id", pg.UUID(as_uuid=True), primary_key=True),
    Column("seller_id", pg.UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False),
    Column("layout_date", Date, nullable=False),
    Column("layout_photo_url", String),
)

# payments — Выплаты бонусов
payments = Table(
    "payments",
    metadata,
    Column("id", pg.UUID(as_uuid=True), primary_key=True),
    Column("seller_id", pg.UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False),
    Column("payment_date", Date, nullable=False),
    Column("amount", Integer, nullable=False),
)

# seller_stats — Статистика по продавцу
seller_stats = Table(
    "seller_stats",
    metadata,
    Column("seller_id", pg.UUID(as_uuid=True), ForeignKey("sellers.id"), primary_key=True),
    Column("total_sold", Integer),
    Column("total_bonus", Integer),
    Column("unpaid_bonus", Integer),
)

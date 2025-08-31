from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, String, Integer, Date, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid

from datetime import datetime, timezone
Base = declarative_base()

class Seller(Base):
    __tablename__ = "sellers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registration_date = Column(Date, nullable=False)
    telegram_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    shop_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    bank_name = Column(String, nullable=True)
    card_number = Column(String, nullable=True)
    username = Column(String, nullable=True)

    # Опционально: связи
    sales_reports = relationship("SalesReport", back_populates="seller")
    payments = relationship("Payment", back_populates="seller")
    seller_stats = relationship("SellerStat", back_populates="seller", uselist=False)
    logs_tests = relationship("Logs_test", back_populates="seller")
    test_attempts = relationship("TestAttempt", back_populates="seller")




class TestAttempt(Base):
    """Прохождение теста отдельной сущностью"""
    __tablename__ = "test_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    name = Column(String, nullable=False)
    shop_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    correct_answers = Column(Integer, default=0)
    wrong_answers = Column(String, default="[]")
    current_question_index = Column(Integer, default=0)
    finished = Column(Boolean, default=False)

    seller = relationship("Seller", back_populates="test_attempts")


class Logs_test(Base):
    __tablename__ = "logs_test"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    name = Column(String, nullable=False)
    shop_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    correct_answers = Column(Integer, nullable=False, default=0)
    exam_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    wrong_answers = Column(String, default=None)

    seller = relationship("Seller", back_populates="logs_tests")

class SalesReport(Base):
    __tablename__ = "sales_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    name = Column(String, nullable=False)
    shop_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    report_date = Column(Date, nullable=False)
    sold_quantity = Column(Integer, nullable=False)
    receipt_photo_url = Column(String, nullable=True)
    moderation_passed = Column(Boolean, nullable=True)

    seller = relationship("Seller", back_populates="sales_reports")



class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    name = Column(String, nullable=False)
    shop_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Integer, nullable=False)

    seller = relationship("Seller", back_populates="payments")


class SellerStat(Base):
    __tablename__ = "seller_stats"

    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), primary_key=True)
    name = Column(String, nullable=False)
    shop_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    total_sold = Column(Integer, nullable=True)
    total_bonus = Column(Integer, nullable=True)
    unpaid_bonus = Column(Integer, nullable=True)

    seller = relationship("Seller", back_populates="seller_stats")


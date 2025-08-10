from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, String, Integer, Date, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import date

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
    exams = relationship("Exam", back_populates="seller")
    sales_reports = relationship("SalesReport", back_populates="seller")
    layouts = relationship("Layout", back_populates="seller")
    payments = relationship("Payment", back_populates="seller")
    seller_stats = relationship("SellerStat", back_populates="seller", uselist=False)


class Exam(Base):
    __tablename__ = "exams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    exam_date = Column(Date, nullable=False, default=date.today)
    correct_answers = Column(Integer, nullable=False, default=0)
    active_answer = Column(Integer, nullable=False, default=0)
    active_question = Column(Integer, nullable=False, default=0)  # индекс текущего вопроса (в тесте или обучении)
    start_education = Column(Boolean, default=False)
    end_education = Column(Boolean, default=False)
    wrong_answers = Column(String, default=None)

    seller = relationship("Seller", back_populates="exams")



class SalesReport(Base):
    __tablename__ = "sales_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    report_date = Column(Date, nullable=False)
    sold_quantity = Column(Integer, nullable=False)
    receipt_photo_url = Column(String, nullable=True)
    moderation_passed = Column(Boolean, nullable=True)

    seller = relationship("Seller", back_populates="sales_reports")



class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Integer, nullable=False)

    seller = relationship("Seller", back_populates="payments")


class SellerStat(Base):
    __tablename__ = "seller_stats"

    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), primary_key=True)
    total_sold = Column(Integer, nullable=True)
    total_bonus = Column(Integer, nullable=True)
    unpaid_bonus = Column(Integer, nullable=True)

    seller = relationship("Seller", back_populates="seller_stats")

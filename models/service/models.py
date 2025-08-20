from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Integer, Boolean, Text, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()

class Bonus(Base):
    __tablename__ = "bonuses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    amount = Column(Integer, nullable=True)
    condition = Column(Text, nullable=True)
    frequency = Column(String, nullable=True)
    active = Column(Boolean, default=True)


class LearningCard(Base):
    __tablename__ = "learning_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_number = Column(Integer, nullable=True)
    lesson_text = Column(Text, nullable=False)
    image_urls = Column(Text, nullable=True)  # можно хранить JSON или строку с разделением запятой
    question = Column(Text, nullable=False)
    option_1 = Column(Text, nullable=False)
    option_2 = Column(Text, nullable=False)
    option_3 = Column(Text, nullable=False)
    option_4 = Column(Text, nullable=False)
    correct_option_index = Column(Text, nullable=False)
    test_image_urls = Column(Text,nullable=False)

class FakeChart (Base):
    __tablename__ = "fake_chart"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_name = Column(Text, nullable=False)
    total_bonus = Column(Integer, nullable=False)

class fake_users_stats (Base):
    __tablename__ = "fake_users_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fake_active = Column(Boolean, nullable=False)
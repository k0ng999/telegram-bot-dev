import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
user_engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=user_engine, autoflush=False, autocommit=False)
metadata = MetaData()

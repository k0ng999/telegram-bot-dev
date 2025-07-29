import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker

load_dotenv()

SERVICES_DATABASE_URL = os.getenv("SERVICES_DATABASE_URL")
services_engine = create_engine(SERVICES_DATABASE_URL)
metadata = MetaData()

SessionLocal = sessionmaker(bind=services_engine)

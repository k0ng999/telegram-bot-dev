import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
user_engine = create_engine(DATABASE_URL)
metadata = MetaData()

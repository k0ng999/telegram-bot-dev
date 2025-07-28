import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData

load_dotenv()

SERVICES_DATABASE_URL = os.getenv("SERVICES_DATABASE_URL")
services_engine = create_engine(SERVICES_DATABASE_URL)
metadata = MetaData()

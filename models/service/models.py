from sqlalchemy import Table, Column, String, Integer, Boolean, Text, MetaData
import sqlalchemy.dialects.postgresql as pg

metadata_services = MetaData()

bonuses = Table(
    "bonuses",
    metadata_services,
    Column("id", pg.UUID(as_uuid=True), primary_key=True),
    Column("name", String, nullable=False),
    Column("description", Text),
    Column("amount", Integer),
    Column("condition", Text),
    Column("frequency", String),
    Column("active", Boolean, default=True),
)

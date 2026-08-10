from sqlalchemy import create_engine, MetaData
import sqlalchemy as sa
import os
from dotenv import load_dotenv
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
connection = engine.connect()
metadata = MetaData()
user_table = sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("email", sa.String),
    sa.Column("username", sa.String),
    sa.Column("created_at", sa.DateTime)
)
connected_accounts_table = sa.Table(
    "connected_accounts",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
    sa.Column("provider", sa.String),
    sa.Column("provider_id", sa.Integer),
    sa.Column("created_at", sa.DateTime)
)
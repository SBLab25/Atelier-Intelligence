import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

from config import DATABASE_URL
db = DATABASE_URL
engine = create_engine(db)
with engine.connect() as conn:
    conn.execute(text("ALTER TABLE tracking_events ALTER COLUMN metadata TYPE jsonb USING metadata::jsonb;"))
    conn.commit()

import sqlalchemy
from sqlalchemy.dialects import postgresql
print("sqlalchemy", sqlalchemy.__version__)
print("default postgresql:// driver =", postgresql.dialect.driver)
for mod in ("psycopg2", "psycopg"):
    try:
        __import__(mod); print(mod, "importable")
    except Exception as e:
        print(mod, "NOT importable:", type(e).__name__)

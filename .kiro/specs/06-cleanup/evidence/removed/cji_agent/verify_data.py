import duckdb, pathlib, sys

parquet = pathlib.Path("data/events.parquet")
if not parquet.exists():
    print("ERROR: data/events.parquet not found")
    sys.exit(1)

conn = duckdb.connect()
try:
    result = conn.execute(
        f"SELECT COUNT(DISTINCT user_id), COUNT(*) FROM read_parquet('{parquet.as_posix()}')"
    ).fetchone()
    users, events = result
    print(f"Sessions (unique users): {users:,}")
    print(f"Total events:            {events:,}")
    if users >= 1000:
        print("Data verification: OK")
    else:
        print(f"WARNING: Expected ~2000 users, got {users}")
finally:
    conn.close()

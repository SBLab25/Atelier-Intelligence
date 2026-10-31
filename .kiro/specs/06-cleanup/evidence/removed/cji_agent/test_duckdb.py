import duckdb
from pathlib import Path

def test():
    print("Testing DuckDB initialization")
    e = Path('data/events.parquet').resolve().as_posix()
    print("Events file:", e)
    conn = duckdb.connect(':memory:')
    conn.execute('PRAGMA threads=1')
    conn.execute(f"CREATE OR REPLACE TEMP VIEW events AS SELECT * FROM read_parquet('{e}')")
    print("Done views!")
    df = conn.execute("SELECT step_id, COUNT(*) FROM events GROUP BY step_id").df()
    print("Dataframe:")
    print(df)
    print("Success")

if __name__ == '__main__':
    test()

import asyncio
import duckdb
from pathlib import Path

async def main():
    print('Starting')
    conn = duckdb.connect(':memory:')
    conn.execute('PRAGMA threads=1')
    e = Path('cji_agent/data/events.parquet').resolve().as_posix()
    print(f'Path: {e}')
    q = f"CREATE OR REPLACE TEMP VIEW events AS SELECT * FROM read_parquet('{e}')"
    print(q)
    conn.execute(q)
    print('Done query')

if __name__ == '__main__':
    asyncio.run(main())

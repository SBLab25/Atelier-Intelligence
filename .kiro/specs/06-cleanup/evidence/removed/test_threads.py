import concurrent.futures
import sys
import os

sys.path.append('cji_agent')
os.environ['CJI_MODE'] = 'demo'

import duckdb
from cji_agent.config import DUCKDB_PATH, EVENTS_PARQUET

def _setup_views(conn):
    conn.execute(f"CREATE OR REPLACE TEMP VIEW events AS SELECT * FROM read_parquet('{EVENTS_PARQUET.resolve().as_posix()}')")

def test():
    print('Testing inside thread with threads=1...')
    conn = duckdb.connect(':memory:')
    conn.execute('PRAGMA threads=1')
    _setup_views(conn)
    df = conn.execute('SELECT count(*) FROM events').df()
    print('Result:', df.iloc[0,0])
    return True

with concurrent.futures.ThreadPoolExecutor() as executor:
    future = executor.submit(test)
    print('Done:', future.result())

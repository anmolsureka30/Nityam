import sys
from pathlib import Path

# Add the project root to sys.path so that shruti can be imported
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest_asyncio
from shruti.db import get_pool, apply_migrations


@pytest_asyncio.fixture
async def db_conn():
    pool = await get_pool()
    await apply_migrations(pool)
    conn = await pool.acquire()
    tx = conn.transaction()
    await tx.start()
    try:
        yield conn
    finally:
        await tx.rollback()
        await pool.release(conn)
        await pool.close()

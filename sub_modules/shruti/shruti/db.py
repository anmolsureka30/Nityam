import os
from pathlib import Path
import asyncpg

_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://shruti:shruti@localhost:5434/shruti"
)


async def get_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(_DATABASE_URL)


async def apply_migrations(pool: asyncpg.Pool, migrations_dir: str = "infra/migrations") -> None:
    files = sorted(Path(migrations_dir).glob("*.sql"))
    async with pool.acquire() as conn:
        for f in files:
            sql = f.read_text()
            try:
                await conn.execute(sql)
            except asyncpg.exceptions.DuplicateTableError:
                continue

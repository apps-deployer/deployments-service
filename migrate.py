"""Simple migration runner — applies all .sql files from migrations/ in order."""

import asyncio
import os
from pathlib import Path

import asyncpg

from src.config import load_settings


async def run_migrations():
    settings = load_settings()
    db = settings.db
    dsn = f"postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.name}"

    conn = await asyncpg.connect(dsn)
    try:
        migrations_dir = Path(os.environ.get("MIGRATIONS_PATH", "migrations"))
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            print(f"Applying {sql_file.name}...")
            sql = sql_file.read_text()
            await conn.execute(sql)
            print(f"  Done.")
    finally:
        await conn.close()

    print("All migrations applied.")


if __name__ == "__main__":
    asyncio.run(run_migrations())

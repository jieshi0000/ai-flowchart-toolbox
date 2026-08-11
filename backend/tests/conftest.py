import os
import subprocess
import time

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AUTH__ENABLED", "false")

import asyncpg
import pytest
from httpx import AsyncClient
from pathlib import Path

SQL_DIR = Path(__file__).parent.parent / "db"
DC_FILE = Path(__file__).parent / "docker-compose.yml"
DB_URL = "postgresql://app:123456@localhost:5432/test_db"
APP_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def uvicorn_server():
    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "src.app.main"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "AUTH__ENABLED": "false", "APP__DEBUG": "false"},
    )
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen(f"{APP_URL}/docs")
            break
        except Exception:
            time.sleep(0.5)
    yield proc
    proc.terminate()
    proc.wait()


@pytest.fixture
async def client(uvicorn_server):
    async with AsyncClient(base_url=APP_URL) as c:
        yield c


@pytest.fixture
async def reset_data():
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("TRUNCATE TABLE demo_product")
        with open(SQL_DIR / "V4__init_demo_product_data.sql") as f:
            sql = f.read()
        await conn.execute(sql)
    finally:
        await conn.close()

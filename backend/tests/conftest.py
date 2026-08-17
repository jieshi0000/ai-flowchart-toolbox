import os
import subprocess
import sys
import time

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AUTH__ENABLED", "false")
os.environ.setdefault("REDIS__URL", "redis://localhost:6389/15")
os.environ.setdefault("MINIO__ACCESS_KEY", "integration-test-access-key")
os.environ.setdefault("MINIO__SECRET_KEY", "integration-test-secret-key")
os.environ.setdefault("AI__PROVIDERS_FILE", "config/providers.example.json")
os.environ.setdefault("DEEPSEEK_API_KEY", "integration-test-provider-key")

import asyncpg
import pytest
from httpx import AsyncClient
from pathlib import Path

SQL_DIR = Path(__file__).parent.parent / "db"
DC_FILE = Path(__file__).parent / "docker-compose.yml"
DB_URL = "postgresql://app:123456@localhost:5432/test_db"
APP_URL = "http://127.0.0.1:10105"


@pytest.fixture(scope="session")
def uvicorn_server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "AUTH__ENABLED": "false", "APP__DEBUG": "false"},
    )
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen(f"{APP_URL}/docs", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
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
        with open(SQL_DIR / "V4__init_demo_product_data.sql", encoding="utf-8") as f:
            sql = f.read()
        await conn.execute(sql)
    finally:
        await conn.close()

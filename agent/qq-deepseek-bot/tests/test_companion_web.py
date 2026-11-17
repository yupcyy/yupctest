import asyncio
import sqlite3

import httpx

from test_building_service import settings
from qq_deepseek.building.api import create_app
from qq_deepseek.storage.companion import SCHEMA


def test_owner_only_web_controls(tmp_path):
    config = settings(tmp_path)
    config.database_type = "sqlite"
    config.database_path = tmp_path / "companion.sqlite"
    config.enable_companion = config.companion_persistence = True
    with sqlite3.connect(config.database_path) as db:
        db.executescript(SCHEMA)
    async def run():
        app = create_app(config)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/companion")).status_code == 401
            await client.post("/api/login", json={"username": "visitor"})
            assert (await client.get("/companion")).status_code == 403
            assert (await client.post("/api/companion", json={})).status_code == 403
            await client.post("/api/admin/login", json={"password": config.building_admin_password})
            assert (await client.post("/api/companion", json={}, headers={"Origin": "http://evil"})).status_code == 403
            assert (await client.post("/api/companion", json={"stopped": True,"profile": "喜欢鱼"})).status_code == 200
            data = (await client.get("/api/companion")).json()
            assert data["control"]["stopped"] and data["profile"]["note"] == "喜欢鱼"
            assert (await client.get("/companion")).status_code == 200
    asyncio.run(run())

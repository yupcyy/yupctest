import asyncio
import io
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
from PIL import Image

from qq_deepseek.building.api import create_app
from qq_deepseek.building.storage import BuildingTask, BuildingTaskStore


def settings(tmp_path):
    return SimpleNamespace(building_storage_path=tmp_path / "tasks", building_token_ttl=3600,
                           master_qq_id=999, building_admin_password="123454321",
                           gomoku_storage_path=tmp_path / "gomoku")


def test_web_login_upload_preview_and_pixel_art(tmp_path):
    async def run():
        app = create_app(settings(tmp_path))
        fixture = Path(__file__).parents[1] / "building-viewer/public/fixtures/test-house.nbt"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/api/login", json={"username": "Alice"})).status_code == 200
            uploaded = await client.post("/api/web/upload", files={
                "file": ("house.nbt", fixture.read_bytes(), "application/octet-stream")})
            assert uploaded.status_code == 200
            history = (await client.get("/api/web/history")).json()["items"]
            assert len(history) == 1 and history[0]["source"] == "upload"
            assert (await client.get(history[0]["url"])).status_code == 200

            source = io.BytesIO(); Image.new("RGB", (640, 320), (20, 120, 220)).save(source, "JPEG")
            pixel = await client.post("/api/web/pixel-art", files={
                "file": ("photo.jpg", source.getvalue(), "image/jpeg")})
            assert pixel.status_code == 200
            assert len((await client.get("/api/web/history")).json()["items"]) == 2
    asyncio.run(run())


def test_expired_upload_token_is_rejected(tmp_path):
    store = BuildingTaskStore(tmp_path / "tasks")
    now = time.time()
    task = BuildingTask("a" * 32, 1, None, "upload", "completed", now, now,
                        "secret", now - 1, source="upload")
    store.save(task)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings(tmp_path))),
                                     base_url="http://test") as client:
            assert (await client.get(f"/api/b/{task.task_id}?token=secret")).status_code == 410
    asyncio.run(run())


def test_username_claim_admin_and_gomoku(tmp_path):
    async def run():
        app = create_app(settings(tmp_path))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as user:
            assert (await user.post("/api/login", json={"username": "Alice"})).status_code == 200
            game = await user.post("/api/gomoku", json={"mode": "agent"})
            assert game.status_code == 200
            game_id = game.json()["game_id"]
            moved = await user.post(f"/api/gomoku/{game_id}/move", json={"x": 7, "y": 7})
            assert moved.status_code == 200
            assert sum(cell != "." for row in moved.json()["board"] for cell in row) == 2
            assert moved.json()["chat"]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as other:
            assert (await other.post("/api/login", json={"username": "Alice"})).status_code == 409
            assert (await other.post("/api/admin/login", json={"password": "123454321"})).status_code == 200
    asyncio.run(run())

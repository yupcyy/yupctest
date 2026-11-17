from __future__ import annotations

import secrets
import time
import uuid
import gzip
import io
import base64
import hashlib
import hmac
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from qq_deepseek.core.config import Settings
from qq_deepseek.providers.deepseek import DeepSeekProvider
from qq_deepseek.services.gomoku_web import GomokuWebService

from .exporters import export_structure_nbt, load_sponge_v2, load_structure_nbt
from .storage import BuildingTask, BuildingTaskStore
from .pixel_art import create_pixel_art

MAX_UPLOAD = 8 * 1024 * 1024
MAX_IMAGE_UPLOAD = 32 * 1024 * 1024
MAX_BLOCKS = 2_000_000
MAX_DIMENSION = 256
MAX_DECOMPRESSED = 64 * 1024 * 1024
SESSION_COOKIE = "dafeiyu_session"


class LoginBody(BaseModel):
    username: str = Field(min_length=2, max_length=24)


class AdminLoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class GameCreateBody(BaseModel):
    mode: str


class GameMoveBody(BaseModel):
    x: int = Field(ge=0, le=14)
    y: int = Field(ge=0, le=14)


class GameChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=300)


class CompanionControlBody(BaseModel):
    stopped: bool = False
    asleep: bool = False
    auto_journal: bool = False
    profile: str = Field(default="", max_length=500)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    store = BuildingTaskStore(settings.building_storage_path)
    app = FastAPI(title="DaFeiYu Building API", docs_url=None, redoc_url=None)
    auth_root = settings.building_storage_path.parent / "web_auth"
    auth_root.mkdir(parents=True, exist_ok=True)
    secret_path = auth_root / ".session_secret"
    if not secret_path.exists():
        secret_path.write_bytes(secrets.token_bytes(32))
        os.chmod(secret_path, 0o600)
    session_secret = secret_path.read_bytes()
    if len(session_secret) < 32:
        raise RuntimeError("invalid building session secret")
    admin_failures: dict[str, list[float]] = {}
    game_provider = None
    if getattr(settings, "api_key", ""):
        game_provider = DeepSeekProvider(settings.api_key, settings.base_url, settings.model)
    gomoku = GomokuWebService(getattr(settings, "gomoku_storage_path",
                                      settings.building_storage_path.parent.parent / "gomoku" / "games"),
                              game_provider)

    @app.on_event("shutdown")
    async def close_game_provider():
        if game_provider is not None:
            await game_provider.close()

    def session_token(payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
        signature = hmac.new(session_secret, encoded, hashlib.sha256).hexdigest().encode()
        return (encoded + b"." + signature).decode()

    def read_session(request: Request) -> dict | None:
        value = request.cookies.get(SESSION_COOKIE, "")
        try:
            encoded, signature = value.rsplit(".", 1)
            expected = hmac.new(session_secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            payload = json.loads(raw)
            return payload if float(payload.get("exp", 0)) > time.time() else None
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def normalized_username(value: str) -> str:
        value = " ".join(value.strip().split())
        if not re.fullmatch(r"[\w\-\u4e00-\u9fff]{2,24}", value, re.UNICODE):
            raise HTTPException(422, "用户名仅允许中文、字母、数字、下划线和短横线")
        return value.casefold()

    def claim_path(username: str) -> Path:
        return auth_root / (hashlib.sha256(username.encode()).hexdigest() + ".json")

    def require_web_session(request: Request) -> dict:
        session = read_session(request)
        if not session:
            raise HTTPException(401, "please log in")
        return session

    def authorized(task_id: str, token: str, authorization: str | None) -> BuildingTask:
        try:
            task = store.load(task_id)
        except ValueError:
            task = None
        supplied = token or ((authorization or "").removeprefix("Bearer ").strip())
        if not task or not supplied or not secrets.compare_digest(task.token, supplied):
            raise HTTPException(404, "task not found")
        if task.expires_at < time.time():
            raise HTTPException(410, "token expired")
        return task

    def safe_file(task_id: str, name: str) -> Path:
        folder = store.directory(task_id).resolve()
        path = folder / name
        if path.is_symlink() or not path.is_file() or folder not in path.resolve().parents:
            raise HTTPException(404, "file not found")
        return path

    def task_json(task: BuildingTask) -> dict:
        return {"task_id": task.task_id, "user_id": task.user_id, "group_id": task.group_id,
                "web_username": task.web_username,
                "source": task.source, "request": task.request[:200], "status": task.status,
                "error": task.error,
                "created_at": task.created_at, "updated_at": task.updated_at, "size": task.size,
                "block_count": task.block_count, "expires_at": task.expires_at,
                "url": f"/{'p' if task.source == 'image' else 'b'}/{task.task_id}?token={task.token}"}

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/companion")
    async def companion_page(request: Request):
        session = require_web_session(request)
        if not session.get("admin"):
            raise HTTPException(403, "仅主人可访问")
        page = Path(__file__).with_name("companion.html")
        return HTMLResponse(page.read_text(encoding="utf-8"))

    @app.get("/api/companion")
    async def companion_status(request: Request):
        session = require_web_session(request)
        if not session.get("admin"):
            raise HTTPException(403, "仅主人可访问")
        if settings.database_type != "sqlite":
            raise HTTPException(409, "拟人存储需要已批准的 SQLite 表")
        import sqlite3
        from qq_deepseek.storage.companion import CompanionStore
        def load():
            with sqlite3.connect(f"file:{settings.database_path}?mode=ro", uri=True) as db:
                companion_store = CompanionStore(db)
                return {"enabled": settings.enable_companion,
                        "persistence": settings.companion_persistence,
                        "control": companion_store.load("control") or {},
                        "profile": companion_store.load(f"profile:{settings.master_qq_id}") or {},
                        "journal": companion_store.journal(settings.master_qq_id)}
        import asyncio
        try:
            return await asyncio.to_thread(load)
        except sqlite3.Error:
            raise HTTPException(503, "拟人存储尚未就绪")

    @app.post("/api/companion")
    async def companion_update(body: CompanionControlBody, request: Request):
        session = require_web_session(request)
        if not session.get("admin"):
            raise HTTPException(403, "仅主人可管理")
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "跨站请求已拒绝")
        if settings.database_type != "sqlite":
            raise HTTPException(409, "仅支持已批准的 SQLite 存储")
        import asyncio
        import sqlite3
        def save():
            with sqlite3.connect(f"file:{settings.database_path}?mode=rw", uri=True, timeout=10) as db:
                now = time.time()
                rows = [("control", json.dumps({"stopped": body.stopped, "asleep": body.asleep,
                        "auto_journal": body.auto_journal})),
                        (f"profile:{settings.master_qq_id}", json.dumps({"note": body.profile}, ensure_ascii=False))]
                db.executemany("INSERT INTO agent_companion_state(scope,payload,updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(scope) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                    [(key, value, now) for key, value in rows])
        try:
            await asyncio.to_thread(save)
        except sqlite3.Error:
            raise HTTPException(503, "保存失败，请检查存储权限")
        return {"ok": True}

    @app.post("/api/login")
    async def web_login(body: LoginBody, request: Request):
        username = normalized_username(body.username)
        current = read_session(request)
        path = claim_path(username)
        if path.exists() and not (current and current.get("username") == username):
            raise HTTPException(409, "该用户名已被另一浏览器认领")
        if not path.exists():
            path.write_text(json.dumps({"username": username, "created_at": time.time()}, ensure_ascii=False),
                            encoding="utf-8")
        payload = {"username": username, "admin": False, "exp": time.time() + 30 * 86400}
        response = JSONResponse({"ok": True, "username": username, "redirect": "/dashboard"})
        response.set_cookie(SESSION_COOKIE, session_token(payload), max_age=30 * 86400,
                            httponly=True, samesite="strict", path="/")
        return response

    @app.post("/api/admin/login")
    async def admin_login(body: AdminLoginBody, request: Request):
        address = request.client.host if request.client else "unknown"
        now = time.time()
        failures = [value for value in admin_failures.get(address, []) if now - value < 600]
        if len(failures) >= 5:
            raise HTTPException(429, "登录失败次数过多，请稍后再试")
        expected = getattr(settings, "building_admin_password", "")
        if not expected or not hmac.compare_digest(body.password, expected):
            failures.append(now); admin_failures[address] = failures
            raise HTTPException(401, "密码错误")
        admin_failures.pop(address, None)
        payload = {"username": "主人", "admin": True, "exp": now + 12 * 3600}
        response = JSONResponse({"ok": True, "redirect": "/dashboard"})
        response.set_cookie(SESSION_COOKIE, session_token(payload), max_age=12 * 3600,
                            httponly=True, samesite="strict", path="/")
        return response

    @app.get("/api/session")
    async def session_info(request: Request):
        session = require_web_session(request)
        return {"username": session["username"], "admin": bool(session.get("admin"))}

    @app.post("/api/logout")
    async def logout():
        response = JSONResponse({"ok": True})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/api/web/history")
    async def web_history(request: Request):
        session = require_web_session(request)
        visible = [item for item in store.all() if item.status != "failed"]
        tasks = visible if session.get("admin") else [
            item for item in visible if item.web_username == session["username"]]
        return {"items": [task_json(item) for item in tasks[:200]]}

    @app.post("/api/gomoku")
    async def create_game(body: GameCreateBody, request: Request):
        session = require_web_session(request)
        try:
            game = await gomoku.create(session["username"], body.mode)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"game_id": game["game_id"], "url": f"/gomoku/{game['game_id']}"}

    @app.get("/api/gomoku/{game_id}")
    async def get_game(game_id: str, request: Request):
        session = require_web_session(request)
        game = await gomoku.get(game_id, session["username"], bool(session.get("admin")))
        if not game:
            raise HTTPException(404, "对局不存在或你无权查看")
        return game

    @app.post("/api/gomoku/{game_id}/join")
    async def join_game(game_id: str, request: Request):
        session = require_web_session(request)
        try:
            return await gomoku.join(game_id, session["username"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/gomoku/{game_id}/move")
    async def game_move(game_id: str, body: GameMoveBody, request: Request):
        session = require_web_session(request)
        try:
            return await gomoku.move(game_id, session["username"], body.x, body.y)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/gomoku/{game_id}/chat")
    async def game_chat(game_id: str, body: GameChatBody, request: Request):
        session = require_web_session(request)
        try:
            return await gomoku.chat(game_id, session["username"], body.message)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/web/upload")
    async def web_upload(request: Request, file: UploadFile = File(...)):
        session = require_web_session(request)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".nbt", ".schem", ".schematic"}:
            raise HTTPException(415, "仅接受 .nbt/.schem/.schematic")
        content = await file.read(MAX_UPLOAD + 1)
        if len(content) > MAX_UPLOAD:
            raise HTTPException(413, "文件超过 8 MiB")
        if content[:2] == b"\x1f\x8b":
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
                    if len(stream.read(MAX_DECOMPRESSED + 1)) > MAX_DECOMPRESSED:
                        raise HTTPException(413, "解压后超过 64 MiB")
            except HTTPException:
                raise
            except (OSError, EOFError) as exc:
                raise HTTPException(422, "无效 gzip 文件") from exc
        now, task_id = time.time(), uuid.uuid4().hex
        display_name = Path(file.filename or "upload").name[:100]
        task = BuildingTask(task_id, 0, None, f"上传：{display_name}", "completed", now, now,
                            secrets.token_urlsafe(32), now + settings.building_token_ttl,
                            source="upload", web_username=session["username"])
        folder = store.directory(task_id); folder.mkdir(parents=True)
        source = folder / ("upload" + suffix); source.write_bytes(content)
        try:
            structure = load_structure_nbt(source) if suffix == ".nbt" else load_sponge_v2(source)
            if any(value > MAX_DIMENSION for value in structure.size) or len(structure.blocks) > MAX_BLOCKS:
                raise ValueError("结构尺寸或方块数超过限制")
            export_structure_nbt(structure, folder / "building.nbt")
            task.size, task.block_count = structure.size, len(structure.blocks); store.save(task)
        except Exception as exc:
            for item in folder.iterdir(): item.unlink(missing_ok=True)
            folder.rmdir()
            raise HTTPException(422, f"无法解析建筑文件：{str(exc)[:160]}") from exc
        return {"url": f"/b/{task.task_id}?token={task.token}"}

    @app.post("/api/web/pixel-art")
    async def web_pixel_art(request: Request, file: UploadFile = File(...)):
        session = require_web_session(request)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise HTTPException(415, "仅接受 JPEG、PNG、WebP")
        content = await file.read(MAX_IMAGE_UPLOAD + 1)
        if len(content) > MAX_IMAGE_UPLOAD:
            raise HTTPException(413, "图片超过 32 MiB")
        try:
            result, dimensions = create_pixel_art(content)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        now, task_id = time.time(), uuid.uuid4().hex
        task = BuildingTask(task_id, 0, None, f"像素画：{Path(file.filename or 'image').name[:100]}",
                            "completed", now, now, secrets.token_urlsafe(32),
                            now + settings.building_token_ttl, size=(dimensions[0], dimensions[1], 1),
                            source="image", web_username=session["username"])
        folder = store.directory(task_id); folder.mkdir(parents=True)
        (folder / "pixel-art.png").write_bytes(result); store.save(task)
        return {"url": f"/p/{task.task_id}?token={task.token}"}

    @app.get("/api/b/{task_id}")
    async def metadata(task_id: str, token: str = Query(""), authorization: str | None = Header(None)):
        task = authorized(task_id, token, authorization)
        return {"task_id": task.task_id, "status": task.status, "size": task.size,
                "block_count": task.block_count, "spec": task.spec, "error": task.error,
                "source": task.source, "expires_at": task.expires_at}

    @app.get("/api/b/{task_id}/download/{kind}")
    async def download(task_id: str, kind: str, token: str = Query(""),
                       authorization: str | None = Header(None)):
        task = authorized(task_id, token, authorization)
        names = {"nbt": "building.nbt", "schem": "building.schem"}
        if kind not in names or task.status != "completed":
            raise HTTPException(404, "file not found")
        path = safe_file(task_id, names[kind])
        return Response(path.read_bytes(), media_type="application/octet-stream", headers={
            "Content-Disposition": f'attachment; filename="{task_id[:8]}.{kind}"'})

    @app.get("/api/b/{task_id}/history")
    async def history(task_id: str, token: str = Query(""), authorization: str | None = Header(None)):
        anchor = authorized(task_id, token, authorization)
        is_master = bool(settings.master_qq_id and anchor.user_id == settings.master_qq_id)
        visible = [item for item in store.all() if item.status != "failed"]
        tasks = visible if is_master else [item for item in visible if item.user_id == anchor.user_id]
        return {"scope": "all" if is_master else "self", "user_id": anchor.user_id,
                "items": [task_json(item) for item in tasks[:200]]}

    @app.post("/api/b/{anchor_id}/upload")
    async def upload(anchor_id: str, file: UploadFile = File(...), token: str = Query(""),
                     authorization: str | None = Header(None)):
        anchor = authorized(anchor_id, token, authorization)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".nbt", ".schem", ".schematic"}:
            raise HTTPException(415, "only .nbt/.schem/.schematic are accepted")
        content = await file.read(MAX_UPLOAD + 1)
        if len(content) > MAX_UPLOAD:
            raise HTTPException(413, "file exceeds 8 MiB")
        if content[:2] == b"\x1f\x8b":
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
                    if len(stream.read(MAX_DECOMPRESSED + 1)) > MAX_DECOMPRESSED:
                        raise HTTPException(413, "decompressed NBT exceeds 64 MiB")
            except HTTPException:
                raise
            except (OSError, EOFError) as exc:
                raise HTTPException(422, "invalid gzip stream") from exc
        now, task_id = time.time(), uuid.uuid4().hex
        display_name = Path(file.filename or "upload").name[:100]
        task = BuildingTask(task_id, anchor.user_id, anchor.group_id, f"上传：{display_name}",
                            "completed", now, now, secrets.token_urlsafe(32),
                            now + settings.building_token_ttl, notification_sent=True, source="upload",
                            web_username=anchor.web_username)
        folder = store.directory(task_id)
        folder.mkdir(parents=True)
        source = folder / ("upload" + suffix)
        source.write_bytes(content)
        try:
            structure = load_structure_nbt(source) if suffix == ".nbt" else load_sponge_v2(source)
            if any(value > MAX_DIMENSION for value in structure.size):
                raise ValueError("dimension exceeds 256")
            if len(structure.blocks) > MAX_BLOCKS:
                raise ValueError("block count exceeds 2,000,000")
            export_structure_nbt(structure, folder / "building.nbt")
            task.size, task.block_count = structure.size, len(structure.blocks)
            store.save(task)
        except Exception as exc:
            for item in folder.iterdir():
                item.unlink(missing_ok=True)
            folder.rmdir()
            raise HTTPException(422, f"invalid building file: {str(exc)[:160]}") from exc
        return {"task_id": task.task_id, "token": task.token, "expires_at": task.expires_at,
                "url": f"/b/{task.task_id}?token={task.token}"}

    @app.post("/api/upload")
    async def unbound_upload_disabled():
        raise HTTPException(401, "upload must be opened from an authorized QQ building task")

    @app.post("/api/b/{anchor_id}/pixel-art")
    async def pixel_art(anchor_id: str, file: UploadFile = File(...), token: str = Query(""),
                        authorization: str | None = Header(None)):
        anchor = authorized(anchor_id, token, authorization)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise HTTPException(415, "only JPEG, PNG and WebP are accepted")
        content = await file.read(MAX_IMAGE_UPLOAD + 1)
        if len(content) > MAX_IMAGE_UPLOAD:
            raise HTTPException(413, "image exceeds 32 MiB")
        try:
            result, dimensions = create_pixel_art(content)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        now, task_id = time.time(), uuid.uuid4().hex
        display_name = Path(file.filename or "image").name[:100]
        task = BuildingTask(task_id, anchor.user_id, anchor.group_id, f"像素画：{display_name}",
                            "completed", now, now, secrets.token_urlsafe(32),
                            now + settings.building_token_ttl, size=(dimensions[0], dimensions[1], 1),
                            notification_sent=True, source="image", web_username=anchor.web_username)
        folder = store.directory(task_id)
        folder.mkdir(parents=True)
        (folder / "pixel-art.png").write_bytes(result)
        store.save(task)
        return {"task_id": task.task_id, "token": task.token, "expires_at": task.expires_at,
                "url": f"/p/{task.task_id}?token={task.token}"}

    @app.get("/api/b/{task_id}/pixel-art")
    async def pixel_art_file(task_id: str, token: str = Query(""),
                             authorization: str | None = Header(None), download: bool = Query(False)):
        task = authorized(task_id, token, authorization)
        if task.source != "image":
            raise HTTPException(404, "image not found")
        path = safe_file(task_id, "pixel-art.png")
        headers = ({"Content-Disposition": f'attachment; filename="{task_id[:8]}-pixel-art.png"'}
                   if download else {})
        return Response(path.read_bytes(), media_type="image/png", headers=headers)

    viewer = Path(__file__).resolve().parents[3] / "building-viewer" / "dist"

    @app.get("/")
    async def home():
        index = viewer / "index.html"
        if not index.is_file():
            raise HTTPException(503, "viewer has not been built")
        return HTMLResponse(index.read_text(encoding="utf-8"))

    @app.get("/dashboard")
    async def dashboard():
        index = viewer / "index.html"
        return HTMLResponse(index.read_text(encoding="utf-8"))

    @app.get("/oalogin")
    async def owner_login_page():
        index = viewer / "index.html"
        return HTMLResponse(index.read_text(encoding="utf-8"))

    @app.get("/gomoku/{game_id}")
    async def gomoku_page(game_id: str):
        index = viewer / "index.html"
        return HTMLResponse(index.read_text(encoding="utf-8"))

    @app.get("/b/{task_id}")
    async def preview(task_id: str, token: str = Query(""), authorization: str | None = Header(None)):
        authorized(task_id, token, authorization)
        index = viewer / "index.html"
        if not index.is_file():
            raise HTTPException(503, "viewer has not been built")
        return HTMLResponse(index.read_text(encoding="utf-8"))

    @app.get("/p/{task_id}")
    async def pixel_preview(task_id: str, token: str = Query(""), authorization: str | None = Header(None)):
        task = authorized(task_id, token, authorization)
        if task.source != "image":
            raise HTTPException(404, "image not found")
        index = viewer / "index.html"
        if not index.is_file():
            raise HTTPException(503, "viewer has not been built")
        return HTMLResponse(index.read_text(encoding="utf-8"))

    @app.get("/assets/{asset:path}")
    async def assets(asset: str):
        path = (viewer / "assets" / asset).resolve()
        if viewer.resolve() not in path.parents or not path.is_file():
            raise HTTPException(404)
        media = "text/css" if path.suffix == ".css" else "application/javascript"
        return Response(path.read_bytes(), media_type=media)

    @app.get("/mcmeta/{resource:path}")
    async def mcmeta(resource: str):
        root = (viewer / "mcmeta").resolve()
        path = (root / resource).resolve()
        if root not in path.parents or path.is_symlink() or not path.is_file():
            raise HTTPException(404)
        media = "image/png" if path.suffix == ".png" else "application/json"
        return Response(path.read_bytes(), media_type=media, headers={
            "Cache-Control": "public, max-age=604800, immutable"})

    return app


def main() -> None:
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8787, access_log=False)

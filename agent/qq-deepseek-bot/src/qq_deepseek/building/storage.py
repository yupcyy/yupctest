from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class BuildingTask:
    """Metadata for uploaded preview artifacts; generation is intentionally absent."""
    task_id: str
    user_id: int
    group_id: int | None
    request: str
    status: str
    created_at: float
    updated_at: float
    token: str
    expires_at: float
    spec: dict | None = None
    error: str = ""
    size: tuple[int, int, int] | None = None
    block_count: int = 0
    notification_sent: bool = True
    source: str = "upload"
    web_username: str = ""


class BuildingTaskStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, task_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", task_id):
            raise ValueError("invalid task id")
        path = self.root / task_id
        if path.is_symlink():
            raise ValueError("task directory must not be a symlink")
        return path

    def save(self, task: BuildingTask) -> None:
        folder = self.directory(task.task_id)
        folder.mkdir(parents=True, exist_ok=True)
        target, temporary = folder / "task.json", folder / "task.json.tmp"
        temporary.write_text(json.dumps(asdict(task), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    def load(self, task_id: str) -> BuildingTask | None:
        path = self.directory(task_id) / "task.json"
        if not path.is_file():
            return None
        if path.is_symlink() or path.stat().st_size > 128 * 1024:
            raise ValueError("unsafe task metadata")
        if self.root.resolve() not in path.resolve().parents:
            raise ValueError("task metadata escaped storage root")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("size") is not None:
            data["size"] = tuple(data["size"])
        return BuildingTask(**data)

    def all(self) -> list[BuildingTask]:
        tasks = []
        for path in self.root.iterdir():
            if not path.is_dir() or path.is_symlink() or not re.fullmatch(r"[0-9a-f]{32}", path.name):
                continue
            try:
                task = self.load(path.name)
                if task and task.source in {"upload", "image"}:
                    tasks.append(task)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                log.warning("Ignored unsafe preview task directory %s", path.name)
        return sorted(tasks, key=lambda item: item.created_at, reverse=True)

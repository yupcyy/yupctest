from __future__ import annotations

from collections import Counter
from pydantic import BaseModel


class BlockState(BaseModel, frozen=True):
    name: str
    properties: tuple[tuple[str, str], ...] = ()

    @classmethod
    def create(cls, name: str, properties: dict[str, str] | None = None):
        return cls(name=name, properties=tuple(sorted((properties or {}).items())))

    def palette_key(self) -> str:
        if not self.properties:
            return self.name
        return self.name + "[" + ",".join(f"{k}={v}" for k, v in self.properties) + "]"


class BlockStructure:
    def __init__(self):
        self.blocks: dict[tuple[int, int, int], BlockState] = {}

    def set(self, x: int, y: int, z: int, name: str, properties: dict[str, str] | None = None):
        if min(x, y, z) < 0:
            raise ValueError("block coordinates must be non-negative")
        self.blocks[(x, y, z)] = BlockState.create(name, properties)

    def fill(self, start: tuple[int, int, int], end: tuple[int, int, int], name: str,
             properties: dict[str, str] | None = None):
        for x in range(start[0], end[0] + 1):
            for y in range(start[1], end[1] + 1):
                for z in range(start[2], end[2] + 1):
                    self.set(x, y, z, name, properties)

    def remove(self, x: int, y: int, z: int):
        self.blocks.pop((x, y, z), None)

    @property
    def size(self) -> tuple[int, int, int]:
        if not self.blocks:
            return (0, 0, 0)
        return tuple(max(pos[i] for pos in self.blocks) + 1 for i in range(3))

    def statistics(self) -> dict[str, int]:
        return dict(Counter(state.name for state in self.blocks.values()))

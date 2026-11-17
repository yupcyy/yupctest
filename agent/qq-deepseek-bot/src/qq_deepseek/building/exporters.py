from __future__ import annotations

from pathlib import Path

import nbtlib
import numpy as np
from nbtlib import ByteArray, Compound, File, Int, IntArray, List, Short, String

from .models import BlockState, BlockStructure

DATA_VERSION_1_20_1 = 3465


def _state_nbt(state: BlockState) -> Compound:
    value = Compound({"Name": String(state.name)})
    if state.properties:
        value["Properties"] = Compound({key: String(item) for key, item in state.properties})
    return value


def export_structure_nbt(structure: BlockStructure, path: str | Path) -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    palette = sorted(set(structure.blocks.values()), key=lambda state: state.palette_key())
    indices = {state: index for index, state in enumerate(palette)}
    blocks = [Compound({"pos": List[Int](pos), "state": Int(indices[state])})
              for pos, state in sorted(structure.blocks.items(), key=lambda item: (item[0][1], item[0][2], item[0][0]))]
    root = Compound({"DataVersion": Int(DATA_VERSION_1_20_1), "size": List[Int](structure.size),
                     "palette": List[Compound]([_state_nbt(state) for state in palette]),
                     "blocks": List[Compound](blocks), "entities": List[Compound]([])})
    File(root, gzipped=True).save(path)
    return path


def _varint(value: int) -> list[int]:
    result = []
    while True:
        byte = value & 0x7F
        value >>= 7
        result.append(byte | (0x80 if value else 0))
        if not value:
            return result


def export_sponge_v2(structure: BlockStructure, path: str | Path) -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    palette = sorted(set(structure.blocks.values()), key=lambda state: state.palette_key())
    indices = {state: index for index, state in enumerate(palette)}
    sx, sy, sz = structure.size
    encoded = []
    air = BlockState.create("minecraft:air")
    if air not in indices:
        palette.insert(0, air); indices = {state: index for index, state in enumerate(palette)}
    for y in range(sy):
        for z in range(sz):
            for x in range(sx):
                encoded.extend(_varint(indices[structure.blocks.get((x, y, z), air)]))
    schematic = Compound({
        "Version": Int(2), "DataVersion": Int(DATA_VERSION_1_20_1),
        "Width": Short(sx), "Height": Short(sy), "Length": Short(sz),
        "PaletteMax": Int(len(palette)),
        "Palette": Compound({state.palette_key(): Int(index) for state, index in indices.items()}),
        "BlockData": ByteArray(np.asarray([v if v < 128 else v - 256 for v in encoded], dtype=np.int8)),
        "BlockEntities": List[Compound]([]), "Entities": List[Compound]([]),
        "Offset": IntArray([0, 0, 0]), "Metadata": Compound({"Name": String("DaFeiYu Building")}),
    })
    File(Compound({"Schematic": schematic}), gzipped=True).save(path)
    return path


def load_structure_nbt(path: str | Path) -> BlockStructure:
    root = nbtlib.load(path)
    palette = []
    for value in root["palette"]:
        props = {str(k): str(v) for k, v in value.get("Properties", {}).items()}
        palette.append(BlockState.create(str(value["Name"]), props))
    out = BlockStructure()
    for value in root["blocks"]:
        out.blocks[tuple(int(v) for v in value["pos"])] = palette[int(value["state"])]
    return out


def _read_varints(values) -> list[int]:
    result, current, shift = [], 0, 0
    for raw in values:
        byte = int(raw) & 0xFF
        current |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            result.append(current); current = 0; shift = 0
    if shift:
        raise ValueError("truncated Sponge varint")
    return result


def load_sponge_v2(path: str | Path) -> BlockStructure:
    root = nbtlib.load(path)["Schematic"]
    sx, sy, sz = int(root["Width"]), int(root["Height"]), int(root["Length"])
    palette = [None] * int(root["PaletteMax"])
    for raw, index in root["Palette"].items():
        name, _, suffix = str(raw).partition("[")
        props = {}
        if suffix:
            props = dict(item.split("=", 1) for item in suffix.rstrip("]").split(","))
        palette[int(index)] = BlockState.create(name, props)
    indices = _read_varints(root["BlockData"])
    if len(indices) != sx * sy * sz:
        raise ValueError("Sponge BlockData volume mismatch")
    out = BlockStructure(); offset = 0
    for y in range(sy):
        for z in range(sz):
            for x in range(sx):
                state = palette[indices[offset]]; offset += 1
                if state and state.name != "minecraft:air": out.blocks[(x, y, z)] = state
    return out

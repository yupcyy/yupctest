#!/usr/bin/env python3
"""List NapCat AI voice characters for a group without printing credentials."""
import argparse
import asyncio
import json
import uuid
from pathlib import Path

import websockets
from dotenv import dotenv_values


async def query(group_id: int, env_path: Path):
    env = dotenv_values(env_path)
    url = env.get("NAPCAT_WS_URL", "ws://127.0.0.1:3001")
    token = env.get("NAPCAT_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with websockets.connect(url, additional_headers=headers) as ws:
        echo = str(uuid.uuid4())
        await ws.send(json.dumps({"action":"get_ai_characters", "params":{
            "group_id":group_id, "chat_type":1}, "echo":echo}))
        while True:
            response = json.loads(await asyncio.wait_for(ws.recv(), 20))
            if str(response.get("echo")) != echo: continue
            if response.get("status") != "ok" or response.get("retcode") != 0:
                raise RuntimeError(response.get("message") or response.get("wording") or "NapCat 查询失败")
            data = response.get("data") or []
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return


def main():
    parser = argparse.ArgumentParser(description="列出指定群可用的 NapCat AI 语音角色")
    parser.add_argument("group_id", type=int, help="机器人已加入的群号")
    args = parser.parse_args()
    env_path = Path(__file__).resolve().parents[1] / ".env"
    asyncio.run(query(args.group_id, env_path))


if __name__ == "__main__": main()

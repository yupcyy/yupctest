from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    kind: str
    user_id: int
    group_id: int | None
    self_id: int
    text: str
    mentioned: bool
    context: str = ""

    @property
    def conversation_id(self) -> str:
        if self.kind == "group":
            return f"group:{self.group_id}:user:{self.user_id}"
        return f"private:{self.user_id}"


def parse_message(event: dict) -> Message | None:
    if event.get("post_type") != "message":
        return None
    kind = event.get("message_type")
    if kind not in ("private", "group"):
        return None
    try:
        user_id = int(event["user_id"])
        self_id = int(event["self_id"])
        group_id = int(event["group_id"]) if kind == "group" else None
    except (ValueError, KeyError, TypeError):
        return None
    if user_id == self_id:
        return None
    segments = event.get("message", [])
    if isinstance(segments, list):
        text = "".join(str(s.get("data", {}).get("text", "")) for s in segments if s.get("type") == "text")
        mentioned = any(s.get("type") == "at" and str(s.get("data", {}).get("qq")) == str(self_id) for s in segments)
    else:
        import re
        raw = str(event.get("raw_message", segments))
        mentioned = bool(re.search(r"\[CQ:at,qq=" + re.escape(str(self_id)) + r"(?:,|\])", raw))
        text = re.sub(r"\[CQ:[^\]]*\]", "", raw)
    return Message(kind, user_id, group_id, self_id, text.strip(), mentioned)

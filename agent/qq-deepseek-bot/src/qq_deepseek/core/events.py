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
    event_id: str = ""
    mentioned_user_ids: tuple[int, ...] = ()
    resolved_user_ids: tuple[int, ...] = ()

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
    import re
    if isinstance(segments, list):
        targets = [str(s.get("data", {}).get("qq", "")) for s in segments if s.get("type") == "at"]
    else:
        targets = re.findall(r"\[CQ:at,qq=(\d+)(?:,|\])", raw)
    target_ids = tuple(dict.fromkeys(int(q) for q in targets if q.isdigit() and int(q) > 0 and int(q) != self_id))[:5]
    return Message(kind, user_id, group_id, self_id, text.strip(), mentioned,
                   event_id=str(event["message_id"]) if event.get("message_id") is not None else "",
                   mentioned_user_ids=target_ids)

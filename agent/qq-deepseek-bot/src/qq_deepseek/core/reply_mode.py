
"""Select reply length without additional LLM requests."""

import re
from dataclasses import dataclass
from enum import Enum


class ReplyMode(str, Enum):
    CHAT = "chat"
    QA = "qa"
    TECHNICAL = "technical"
    DETAILED = "detailed"


@dataclass(frozen=True)
class ReplyPolicy:
    chat: int = 120
    qa: int = 220
    technical: int = 500
    detailed: int = 1200

    def max_tokens(self, mode: ReplyMode) -> int:
        return {
            ReplyMode.CHAT: self.chat,
            ReplyMode.QA: self.qa,
            ReplyMode.TECHNICAL: self.technical,
            ReplyMode.DETAILED: self.detailed,
        }[mode]


TECHNICAL_PATTERN = re.compile(
    r"Python|Java|C\+\+|SQL|Linux|Docker|Git|"
    r"API|Agent|Transformer|RAG|代码|编程|"
    r"算法|数据库|模型训练|报错|调试|部署",
    re.IGNORECASE,
)

QA_PATTERN = re.compile(
    r"什么是|为什么|怎么|如何|区别|原理|"
    r"是什么|能不能|是否|解释|介绍|"
    r"查一下|搜索|最新|新闻",
)

DETAIL_PATTERN = re.compile(
    r"详细|完整|一步一步|深入|全面|教程|"
    r"具体步骤|系统讲解|详细解释"
)


def select_reply_mode(
    text: str,
) -> tuple[ReplyMode, str]:
    text = text.strip()

    if text == "/detail":
        return ReplyMode.DETAILED, ""

    if text.startswith("/detail "):
        return ReplyMode.DETAILED, text[8:].strip()

    if text == "/brief":
        return ReplyMode.CHAT, ""

    if text.startswith("/brief "):
        return ReplyMode.CHAT, text[7:].strip()

    if DETAIL_PATTERN.search(text):
        return ReplyMode.DETAILED, text

    if TECHNICAL_PATTERN.search(text):
        return ReplyMode.TECHNICAL, text

    if QA_PATTERN.search(text):
        return ReplyMode.QA, text

    return ReplyMode.CHAT, text

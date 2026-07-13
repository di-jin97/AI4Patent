"""Stable ID generation.

按 design doc Section 6.1 要求：ID 由代码顺序生成，永不重新编号。
"""

from __future__ import annotations

from typing import ClassVar


class IDGenerator:
    """计数器式 ID 生成器。

    用法:
        gen = IDGenerator()
        f1 = gen.next("F")   # "F-001"
        f2 = gen.next("F")   # "F-002"
        d1 = gen.next("DOC") # "DOC-001"

    ID 生成后永不重新编号；删除对象改为 supersededBy 或状态标识。
    """

    _prefixes: ClassVar[dict[str, str]] = {
        "F": "F",
        "FEATURE": "F",
        "DOC": "DOC",
        "DOCUMENT": "DOC",
        "EV": "EV",
        "EVIDENCE": "EV",
        "ROUTE": "ROUTE",
        "Q": "Q",
        "QUERY": "Q",
        "RUN": "RUN",
    }

    _widths: ClassVar[dict[str, int]] = {
        "F": 3,
        "DOC": 3,
        "EV": 3,
        "ROUTE": 3,
        "Q": 3,
        "RUN": 3,
    }

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, prefix: str) -> str:
        canonical = self._prefixes.get(prefix.upper(), prefix.upper())
        width = self._widths.get(canonical, 3)

        if canonical not in self._counters:
            self._counters[canonical] = 0
        self._counters[canonical] += 1
        return f"{canonical}-{self._counters[canonical]:0{width}d}"

    def current(self, prefix: str) -> int:
        canonical = self._prefixes.get(prefix.upper(), prefix.upper())
        return self._counters.get(canonical, 0)

    def reset(self) -> None:
        self._counters.clear()

    @classmethod
    def from_state(cls) -> IDGenerator:
        return cls()

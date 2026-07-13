"""Date utilities.

按 design doc Section 6.3 要求：专利日期必须可机器对比，
晚于 priority_date 的文献不能作为现有技术。
"""

from __future__ import annotations

import re
from datetime import date, datetime

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_US_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_CN_DATE = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$")
_RAW_DATE = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日]?")


def normalize_date(raw: str | None) -> str | None:
    """将常见日期格式转为 ISO 8601 (YYYY-MM-DD)."""
    if not raw or not raw.strip():
        return None
    raw = raw.strip()

    m = _ISO_DATE.fullmatch(raw)
    if m:
        yr, mo, dy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return None

    m = _US_DATE.fullmatch(raw)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"

    m = _CN_DATE.fullmatch(raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    m = _RAW_DATE.search(raw)
    if m:
        yr, mo, dy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1900 <= yr <= 2099 and 1 <= mo <= 12 and 1 <= dy <= 31:
            return f"{yr}-{mo:02d}-{dy:02d}"

    return None


def parse_date(raw: str | None) -> date | None:
    """解析日期字符串为 date 对象."""
    normalized = normalize_date(raw)
    if normalized is None:
        return None
    try:
        return date.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None


def is_before_priority_date(document_date: str | None, priority_date: str | None) -> bool:
    """文档日期早于 priority_date 时返回 True（即不能作为现有技术）"""
    if not document_date or not priority_date:
        return False
    d = parse_date(document_date)
    p = parse_date(priority_date)
    if d is None or p is None:
        return False
    return d < p


def is_valid_prior_art(pub_date: str | None, priority_date: str | None) -> bool:
    """判断文档是否可作为有效现有技术（公开日 <= priority_date）"""
    if not pub_date or not priority_date:
        return False
    d = parse_date(pub_date)
    p = parse_date(priority_date)
    if d is None or p is None:
        return False
    return d <= p


__all__ = ["normalize_date", "parse_date", "is_before_priority_date", "is_valid_prior_art"]

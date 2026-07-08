"""
extract_key_sections.py — 从专利全文里提取关键段（权利要求 + 背景 + 有益效果），截断到 ≤1500 字。

用法：python extract_key_sections.py <text_file>
"""
import re, sys

PATTERNS = {
    "claims":      [r"权\s*利\s*要\s*求\s*(?:书|1[\.、])", r"\bClaim\s*1\b"],
    "background":  [r"背\s*景\s*技\s*术", r"\bBackground\b"],
    "effect":      [r"有\s*益\s*效\s*果", r"发\s*明\s*的\s*有\s*益\s*效\s*果"],
    "next":        [r"具\s*体\s*实\s*施\s*方\s*式", r"附\s*图\s*说\s*明", r"实\s*施\s*例",
                    r"发\s*明\s*内\s*容", r"\bDetailed\s+Description\b", r"\bEmbodiments?\b"],
}

def _find(text, starts, ends, max_chars):
    for sp in starts:
        m = re.search(sp, text, re.IGNORECASE)
        if not m:
            continue
        s = m.start()
        e = len(text)
        for ep in ends:
            em = re.search(ep, text[s+1:], re.IGNORECASE)
            if em:
                e = min(e, s + 1 + em.start())
        seg = text[s:e].strip()
        return seg[:max_chars] + ("..." if len(seg) > max_chars else "")
    return ""

def extract_key_sections(full_text, max_chars=1500):
    if not full_text:
        return ""
    text = re.sub(r"\r\n", "\n", full_text)
    text = re.sub(r"[ \t]+", " ", text)

    claims = _find(text, PATTERNS["claims"],
                   PATTERNS["next"] + PATTERNS["background"] + PATTERNS["effect"] + [r"权\s*利\s*要\s*求\s*[3-9]"],
                   600)
    background = _find(text, PATTERNS["background"],
                       PATTERNS["next"] + PATTERNS["effect"] + PATTERNS["claims"], 500)
    effect = _find(text, PATTERNS["effect"],
                   PATTERNS["next"] + PATTERNS["claims"], 300)

    parts = []
    if claims:     parts.append("【权利要求】\n" + claims)
    if effect:     parts.append("【有益效果】\n" + effect)
    if background: parts.append("【背景技术】\n" + background)

    if not parts:
        return text[:max_chars] + ("..." if len(text) > max_chars else "")

    result = "\n\n".join(parts)
    return result[:max_chars] + ("..." if len(result) > max_chars else "")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python extract_key_sections.py <text_file>")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8", errors="ignore") as f:
        print(extract_key_sections(f.read()))

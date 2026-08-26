import re
def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n{2,}", text.strip()) if p.strip()]
_SENTENCE_END_RE = re.compile(r"(?<=[。！？；\.\!\?;])")
def split_long_paragraph(p: str, max_chars: int) -> list[str]:
    sentences = [s for s in _SENTENCE_END_RE.split(p) if s]
    if len(sentences) <= 1:
        return [p[i:i + max_chars] for i in range(0, len(p), max_chars)] or [p]
    pieces: list[str] = []
    cur = ""
    for s in sentences:
        if len(s) > max_chars:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.extend(s[i:i + max_chars] for i in range(0, len(s), max_chars))
            continue
        if cur and len(cur) + len(s) > max_chars:
            pieces.append(cur)
            cur = ""
        cur += s
    if cur:
        pieces.append(cur)
    return pieces
def chunk_paragraphs(paras: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    def flush():
        nonlocal cur, cur_len
        if cur:
            chunks.append("\n\n".join(cur))
            cur, cur_len = [], 0
    for p in paras:
        if len(p) > max_chars:
            flush()
            for piece in split_long_paragraph(p, max_chars):
                chunks.append(piece)
            continue
        if cur and cur_len + len(p) > max_chars:
            flush()
        cur.append(p)
        cur_len += len(p)
    flush()
    return chunks
def chunk_text(text: str, max_chars: int) -> list[str]:
    paras = split_paragraphs(text)
    return chunk_paragraphs(paras, max_chars) if paras else [text.strip()]

"""Positioned text and table borders from a PDF page.

Two kinds of CAMMED invoice PDFs are handled:
- mPDF files (invoice_NNNNNN.pdf) contain normal text, read with pypdf.
- Invoices printed with the Adobe PDF printer (Acrobat Distiller) draw every
  glyph as an unnamed Type3 shape. Each shape is identified by a fingerprint
  of its outline points, looked up in glyphs.json, which
  tools/make_glyph_table.py builds from the Times New Roman and Arial fonts.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pypdf.generic import ContentStream, NameObject

GLYPHS_FILE = Path(__file__).parent / "glyphs.json"
UNKNOWN = "�"
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


@dataclass
class Run:
    """A piece of text on one baseline."""

    x0: float
    y: float
    text: str
    size: float
    x1: float | None = None  # right edge, when known
    font: str = ""  # PDF base font name, or "times"/"arial" for printed invoices
    bold: bool = False


@dataclass
class Rule:
    """A table border: a stroked line or a thin filled rectangle."""

    horizontal: bool
    lo: float  # thickness band: y range of a horizontal rule, x range of a vertical one
    hi: float
    a: float  # extent along the rule
    b: float

    @property
    def mid(self) -> float:
        return (self.lo + self.hi) / 2


def _mul(m, n):
    """Matrix product m x n, PDF [a b c d e f] convention."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, e * A + f * C + E, e * B + f * D + F)


def _raw(s) -> bytes:
    return s.original_bytes if hasattr(s, "original_bytes") else bytes(s)


# --- Type3 glyph fingerprints ------------------------------------------------

def signature(points) -> str:
    """Fingerprint of a glyph outline given as (x, y) points in 1/4096 em."""
    data = ";".join(f"{x},{y}" for x, y in sorted(set(points)))
    return hashlib.sha1(data.encode()).hexdigest()[:16]


_TOKEN = re.compile(rb"[-+]?(?:\d+\.?\d*|\.\d+)|[A-Za-z'\"*]+\d?")
_NUMBER = re.compile(rb"[-+]?(?:\d+\.?\d*|\.\d+)")


def charproc_points(data: bytes, scale: float) -> list[tuple[int, int]] | None:
    """End points of the path segments of a Type3 glyph procedure, in 1/4096 em.

    scale converts glyph space to em (the font's FontMatrix). Returns None for
    bitmap glyphs, which can't be fingerprinted.
    """
    if b"BI" in data:
        return None
    stack: list[float] = []
    points = []
    m = IDENTITY

    def add(x, y):
        px, py = m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]
        points.append((round(px * scale * 4096), round(py * scale * 4096)))

    for tok in _TOKEN.findall(data):
        if _NUMBER.fullmatch(tok):
            stack.append(float(tok))
            continue
        if tok == b"cm" and len(stack) >= 6:
            m = _mul(tuple(stack[-6:]), m)
        elif tok in (b"m", b"l", b"c", b"v", b"y") and len(stack) >= 2:
            add(stack[-2], stack[-1])
        elif tok == b"re" and len(stack) >= 4:  # rectangular glyphs such as "-" and "l"
            x, y, w, h = stack[-4:]
            for cx, cy in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
                add(cx, cy)
        stack.clear()
    return points


@cache
def glyph_table() -> dict[str, tuple[str, float, str]]:
    """signature -> (character, advance width in em, style flags like "tb")."""
    data = json.loads(GLYPHS_FILE.read_text(encoding="utf-8"))
    return {sig: (v[0], v[1], v[2]) for sig, v in data["glyphs"].items()}


@dataclass
class _Type3Font:
    glyphs: dict[int, tuple[str, float, str]]  # code -> (char, advance in em, style)
    widths: dict[int, float]  # code -> advance in text space units, as the PDF positions it


def _type3_font(font) -> _Type3Font | None:
    if font.get("/Subtype") != "/Type3" or "/ToUnicode" in font:
        return None
    scale = float(font.get("/FontMatrix", [0.001])[0])
    procs = font["/CharProcs"].get_object()
    encoding = font.get("/Encoding")
    encoding = encoding.get_object() if encoding is not None else {}
    names, code = {}, 0
    for d in encoding.get("/Differences", []):
        if isinstance(d, NameObject):
            names[code] = d
            code += 1
        else:
            code = int(d)
    first = int(font.get("/FirstChar", 0))
    widths = {first + i: float(w) * scale for i, w in enumerate(font.get("/Widths", []))}

    table = glyph_table()
    glyphs = {}
    for code, name in names.items():
        proc = procs.get(name)
        points = charproc_points(proc.get_object().get_data(), scale) if proc is not None else None
        if points is None:
            glyphs[code] = (UNKNOWN, 0.5, "")
        elif not points:
            glyphs[code] = (" ", 0.25, "")
        else:
            glyphs[code] = table.get(signature(points), (UNKNOWN, 0.5, ""))
    return _Type3Font(glyphs, widths)


def _type3_runs(page, reader, fonts: dict[str, _Type3Font]) -> list[Run]:
    glyphs = []  # (x, y, char, size, advance in points, style)
    ctm, stack = IDENTITY, []
    tm = tlm = IDENTITY
    font, fsize, tc, tw, th, tl, rise = None, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0

    def show(raw: bytes):
        nonlocal tm
        for code in raw:
            trm = _mul((fsize * th, 0, 0, fsize, 0, rise), _mul(tm, ctm))
            if font is not None:
                char, advance, style = font.glyphs.get(code, (UNKNOWN, 0.5, ""))
                glyphs.append((trm[4], trm[5], char, abs(trm[3]), advance * abs(trm[0]), style))
                w0 = font.widths.get(code, 0.0)
            else:
                w0 = 0.0
            tx = (w0 * fsize + tc + (tw if code == 32 else 0.0)) * th
            tm = _mul((1, 0, 0, 1, tx, 0), tm)

    def next_line(tx, ty):
        nonlocal tm, tlm
        tm = tlm = _mul((1, 0, 0, 1, tx, ty), tlm)

    for operands, op in ContentStream(page.get_contents(), reader).operations:
        if op == b"q":
            stack.append((ctm, font, fsize, tc, tw, th, tl, rise))
        elif op == b"Q" and stack:
            ctm, font, fsize, tc, tw, th, tl, rise = stack.pop()
        elif op == b"cm":
            ctm = _mul(tuple(float(v) for v in operands), ctm)
        elif op == b"BT":
            tm = tlm = IDENTITY
        elif op == b"Tf":
            font, fsize = fonts.get(str(operands[0])), float(operands[1])
        elif op == b"Tc":
            tc = float(operands[0])
        elif op == b"Tw":
            tw = float(operands[0])
        elif op == b"Tz":
            th = float(operands[0]) / 100
        elif op == b"TL":
            tl = float(operands[0])
        elif op == b"Ts":
            rise = float(operands[0])
        elif op == b"Tm":
            tm = tlm = tuple(float(v) for v in operands)
        elif op in (b"Td", b"TD"):
            if op == b"TD":
                tl = -float(operands[1])
            next_line(float(operands[0]), float(operands[1]))
        elif op == b"T*":
            next_line(0, -tl)
        elif op == b"Tj":
            show(_raw(operands[0]))
        elif op == b"'":
            next_line(0, -tl)
            show(_raw(operands[0]))
        elif op == b'"':
            tw, tc = float(operands[0]), float(operands[1])
            next_line(0, -tl)
            show(_raw(operands[2]))
        elif op == b"TJ":
            for item in operands[0]:
                if isinstance(item, (int, float)):
                    tm = _mul((1, 0, 0, 1, -float(item) / 1000 * fsize * th, 0), tm)
                else:
                    show(_raw(item))
    return _group(glyphs)


def _group(glyphs) -> list[Run]:
    """Join glyphs into runs: one run per word, split at spaces and gaps."""
    lines: list[list] = []
    for g in sorted(glyphs, key=lambda g: (-round(g[1], 1), g[0])):
        if lines and abs(lines[-1][0][1] - g[1]) < 0.5:
            lines[-1].append(g)
        else:
            lines.append([g])
    runs = []
    for line in lines:
        cur = None
        for x, y, char, size, advance, style in sorted(line, key=lambda g: g[0]):
            bold = "b" in style
            if char == " ":
                cur = None
            elif cur and x - cur.x1 <= 0.15 * size and bold == cur.bold:
                cur.text += char
                cur.x1 = x + advance
            else:
                family = "arial" if style.startswith("a") else "times"
                cur = Run(x, y, char, size, x + advance, family, bold)
                runs.append(cur)
    return runs


def _text_runs(page) -> list[Run]:
    runs = []

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip():
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            font = str(font_dict.get("/BaseFont", "")) if font_dict else ""
            runs.append(Run(x, y, text, font_size, None, font, "Bold" in font))

    page.extract_text(visitor_text=visit)
    return runs


def page_runs(page, reader) -> list[Run]:
    """All text on the page, as runs with positions in points."""
    fonts = {}
    for name, ref in page.get("/Resources", {}).get("/Font", {}).items():
        t3 = _type3_font(ref.get_object())
        if t3:
            fonts[str(name)] = t3
    return _type3_runs(page, reader, fonts) if fonts else _text_runs(page)


def page_rules(page, reader) -> list[Rule]:
    """Horizontal and vertical table borders drawn on the page."""
    rules = []
    ctm, stack, width = IDENTITY, [], 1.0
    segments, rects, cur, start = [], [], None, None

    def pt(x, y):
        return ctm[0] * x + ctm[2] * y + ctm[4], ctm[1] * x + ctm[3] * y + ctm[5]

    for operands, op in ContentStream(page.get_contents(), reader).operations:
        if op == b"q":
            stack.append((ctm, width))
        elif op == b"Q" and stack:
            ctm, width = stack.pop()
        elif op == b"cm":
            ctm = _mul(tuple(float(v) for v in operands), ctm)
        elif op == b"w":
            width = float(operands[0]) * abs(ctm[0])
        elif op == b"m":
            cur = start = pt(float(operands[0]), float(operands[1]))
        elif op == b"l" and cur:
            nxt = pt(float(operands[0]), float(operands[1]))
            segments.append((*cur, *nxt))
            cur = nxt
        elif op == b"h" and cur:
            segments.append((*cur, *start))
            cur = start
        elif op == b"re":
            x, y, w, h = (float(v) for v in operands)
            (x0, y0), (x1, y1) = pt(x, y), pt(x + w, y + h)
            rects.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        elif op in (b"S", b"s"):
            for x0, y0, x1, y1 in rects:  # stroked rectangle: its four edges
                segments += [(x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)]
            half = width / 2
            for x0, y0, x1, y1 in segments:
                if abs(y0 - y1) < 0.01 and abs(x0 - x1) > 1:
                    rules.append(Rule(True, y0 - half, y0 + half, min(x0, x1), max(x0, x1)))
                elif abs(x0 - x1) < 0.01 and abs(y0 - y1) > 1:
                    rules.append(Rule(False, x0 - half, x0 + half, min(y0, y1), max(y0, y1)))
            segments, rects, cur = [], [], None
        elif op in (b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"):
            for x0, y0, x1, y1 in rects:
                w, h = x1 - x0, y1 - y0
                if h <= 2.5 and w > h:
                    rules.append(Rule(True, y0, y1, x0, x1))
                elif w <= 2.5 and h > w:
                    rules.append(Rule(False, x0, x1, y0, y1))
            segments, rects, cur = [], [], None
        elif op == b"n":
            segments, rects, cur = [], [], None
    return rules

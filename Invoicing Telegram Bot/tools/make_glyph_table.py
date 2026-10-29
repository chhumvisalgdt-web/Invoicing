"""Build glyphs.json: outline fingerprints of Times New Roman and Arial glyphs.

Invoices printed with the Adobe PDF printer draw each glyph as an unnamed
Type3 shape. pdftext.py identifies the shapes by looking up their
fingerprints in glyphs.json. The table holds only fingerprints and advance
widths, not the fonts themselves.

Run on Windows (needs the fonts in C:\\Windows\\Fonts and `pip install fonttools`):
    python tools/make_glyph_table.py
"""

import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pdftext import GLYPHS_FILE, signature  # noqa: E402

FONT_DIR = Path(r"C:\Windows\Fonts")
# Earlier fonts win when two glyphs have the same outline.
FONTS = [
    ("times.ttf", "t"), ("timesbd.ttf", "tb"), ("timesi.ttf", "ti"), ("timesbi.ttf", "tbi"),
    ("arial.ttf", "a"), ("arialbd.ttf", "ab"), ("ariali.ttf", "ai"), ("arialbi.ttf", "abi"),
]
# In priority order: when outlines are identical, the earlier range wins
# (Latin "A" over Greek "Α", Greek "Σ" over the rare Latin "Ʃ").
RANGES = [
    (0x0020, 0x0100),  # Basic Latin, Latin-1
    (0x0370, 0x0400),  # Greek
    (0x2000, 0x20D0),  # punctuation, super/subscripts, currency
    (0x2100, 0x2200),  # letterlike, number forms, arrows
    (0x2200, 0x2300),  # math
    (0x25A0, 0x2600),  # shapes
    (0x0100, 0x0250),  # Latin Extended
]


def outline_points(font: TTFont, glyph_name: str) -> list[tuple[int, int]]:
    """On-curve points and implied on-curve midpoints, in 1/4096 em,
    which is what the Type3 path segments end on."""
    glyf = font["glyf"]
    scale = 4096 / font["head"].unitsPerEm
    coords, ends, flags = glyf[glyph_name].getCoordinates(glyf)
    points, start = [], 0
    for end in ends:
        contour = list(range(start, end + 1))
        for k, i in enumerate(contour):
            x, y = coords[i]
            if flags[i] & 1:
                points.append((round(x * scale), round(y * scale)))
            else:
                j = contour[(k + 1) % len(contour)]
                if not flags[j] & 1:
                    x2, y2 = coords[j]
                    points.append((round((x + x2) / 2 * scale), round((y + y2) / 2 * scale)))
        start = end + 1
    return points


def main() -> None:
    table: dict[str, list] = {}
    clashes = []
    for file, style in FONTS:
        font = TTFont(FONT_DIR / file)
        upm = font["head"].unitsPerEm
        cmap = font.getBestCmap()
        hmtx = font["hmtx"]
        for lo, hi in RANGES:
            for cp in range(lo, hi):
                name = cmap.get(cp)
                if not name:
                    continue
                points = outline_points(font, name)
                if not points:
                    continue
                sig = signature(points)
                char = " " if chr(cp).isspace() else chr(cp)
                entry = [char, round(hmtx[name][0] / upm, 4), style]
                if sig not in table:
                    table[sig] = entry
                elif table[sig][0] != entry[0]:
                    clashes.append((table[sig], entry))
    GLYPHS_FILE.write_text(
        json.dumps({"source": "Times New Roman and Arial outlines, see tools/make_glyph_table.py",
                    "glyphs": table}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"{len(table)} glyphs written to {GLYPHS_FILE} ({GLYPHS_FILE.stat().st_size // 1024} KB)")
    for kept, dropped in clashes:
        print(f"same outline: kept {kept!r}, dropped {dropped!r}")


if __name__ == "__main__":
    main()

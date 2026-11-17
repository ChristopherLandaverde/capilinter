"""Render the README demo image from recorded transcripts.

Reads docs/transcripts/*.txt (real CLI output, see scripts/record_transcripts.sh)
and writes docs/images/fix-demo.svg: a three-step fix on a synthetic payload.
Deterministic and dependency-free, so CI regenerates it and fails on any diff.

Palette and type follow AdLinter's DESIGN.md: warm paper tile, single navy accent,
severity colors reserved for findings. The tile is solid so it reads on GitHub
light and dark themes.

Usage: python scripts/render_readme_images.py
"""

import textwrap
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPTS = ROOT / "docs" / "transcripts"
OUT = ROOT / "docs" / "images" / "fix-demo.svg"

WIDTH = 880
PAD = 32
PANE_PAD = 18
LINE = 18
CHAR = 7.22  # advance width of a 12px monospace glyph
COLS = int((WIDTH - 2 * PAD - 2 * PANE_PAD) / CHAR)

C = {
    "paper": "#FAFAF7",
    "surface": "#FFFFFF",
    "surface2": "#F5F4EE",
    "ink": "#1C1917",
    "muted": "#57534E",
    "border": "#E7E5E0",
    "accent": "#1E3A8A",
    "critical": "#B91C1C",
    "warning": "#B45309",
    "pass": "#166534",
}
SANS = "'General Sans', 'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'Geist Mono', 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

STEPS = [
    ("1 / 3", "The payload sends a raw email", "02-inspect-fail"),
    ("2 / 3", "Normalize and hash it the way Meta documents", "09-hash-repair"),
    ("3 / 3", "Same payload, email hashed: the error clears", "10-inspect-repaired"),
]


def load(name: str) -> list[str]:
    """Transcript lines without the banner, blank lines or the exit marker."""
    lines = (TRANSCRIPTS / f"{name}.txt").read_text(encoding="utf-8").splitlines()
    keep = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("=") or s.startswith("CAPI PAYLOAD RECORD") or s.startswith("[exit"):
            continue
        keep.append(line.rstrip())
    return keep


def wrap(line: str) -> list[str]:
    if len(line) <= COLS:
        return [line]
    indent = " " * (len(line) - len(line.lstrip()) + 12)
    return textwrap.wrap(line, COLS, subsequent_indent=indent, break_long_words=True) or [line]


def color(line: str) -> tuple[str, str]:
    s = line.strip()
    if s.startswith("$ "):
        return C["accent"], "500"
    if s.startswith("×") or s == "Result: FAIL":
        return C["critical"], "600"
    if s.startswith("□ WARNING"):
        return C["warning"], "400"
    if s.startswith("✓") or s == "Result: PASS":
        return C["pass"], "600"
    if s.startswith("Estimated match quality"):
        return C["ink"], "600"
    if s.startswith("+ ") or s.startswith("Matched:") or s.startswith("□ OBSERVED"):
        return C["muted"], "400"
    return C["ink"], "400"


def main() -> None:
    parts: list[str] = []
    y = PAD
    parts.append(
        f'<text x="{PAD}" y="{y + 12}" font-family="{MONO}" font-size="12" letter-spacing="0.96" fill="{C["muted"]}">CAPILINTER / FIX STORY</text>'
    )
    y += 26
    parts.append(
        f'<text x="{PAD}" y="{y + 18}" font-family="{SANS}" font-size="20" font-weight="600" fill="{C["ink"]}">One raw email fails the event. One hash fixes it.</text>'
    )
    y += 44

    for i, (step, title, name) in enumerate(STEPS):
        rows = [(part, *color(line)) for line in load(name) for part in wrap(line)]
        pane_h = PANE_PAD + 22 + LINE * len(rows) + PANE_PAD - 4
        fill = C["surface2"] if i == len(STEPS) - 1 else C["surface"]
        parts.append(
            f'<rect x="{PAD + 0.5}" y="{y + 0.5}" width="{WIDTH - 2 * PAD - 1}" height="{pane_h}" rx="6" fill="{fill}" stroke="{C["border"]}"/>'
        )
        if i == len(STEPS) - 1:
            parts.append(f'<rect x="{PAD}" y="{y}" width="6" height="{pane_h + 1}" rx="3" fill="{C["accent"]}"/>')
        ty = y + PANE_PAD + 10
        parts.append(
            f'<text x="{PAD + PANE_PAD}" y="{ty}" font-family="{MONO}" font-size="11" letter-spacing="0.88" fill="{C["muted"]}">STEP {escape(step)}</text>'
        )
        parts.append(
            f'<text x="{PAD + PANE_PAD + 96}" y="{ty}" font-family="{SANS}" font-size="14" font-weight="600" fill="{C["ink"]}">{escape(title)}</text>'
        )
        ly = ty + 26
        for text, fc, weight in rows:
            parts.append(
                f'<text x="{PAD + PANE_PAD}" y="{ly}" font-family="{MONO}" font-size="12" font-weight="{weight}" fill="{fc}" xml:space="preserve">{escape(text)}</text>'
            )
            ly += LINE
        y += pane_h + 14

    note = "Synthetic fixtures (fixtures/unhashed_pii*.json), real CLI output. Fixed 2024 timestamps cause the staleness warning."
    parts.append(
        f'<text x="{PAD}" y="{y + 12}" font-family="{MONO}" font-size="11" fill="{C["muted"]}">{escape(note)}</text>'
    )
    height = y + 12 + PAD - 4

    label = (
        "Three-step fix on a synthetic Meta CAPI payload. Step 1: capilinter inspect reports RAW_PII_UNHASHED_EMAIL, "
        "estimated match quality 1.0 out of 10, result FAIL. Step 2: capilinter hash normalizes and hashes the email. "
        "Step 3: the same payload with the hashed email has no errors, estimated match quality 4.0 out of 10, result PASS."
    )
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{escape(label)}">',
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="12" fill="{C["paper"]}" stroke="{C["border"]}"/>',
        *parts,
        "</svg>",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(svg), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({WIDTH}x{height})")


if __name__ == "__main__":
    main()

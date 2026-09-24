#!/usr/bin/env python3
"""Concatenate readme_src/*.md (sorted) into README.md and report line count."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parts = sorted((ROOT / "readme_src").glob("*.md"))
text = "\n".join(p.read_text(encoding="utf-8").rstrip() + "\n" for p in parts)
(ROOT / "README.md").write_text(text, encoding="utf-8")
print(f"README.md written ({text.count(chr(10))} lines from {len(parts)} parts)")

# Sanity check: every referenced image exists
import re
missing = [m for m in re.findall(r'(?:src="|\]\()(diagrams/[^")]+)', text) if not (ROOT / m).exists()]
if missing:
    raise SystemExit(f"Missing images: {missing}")
print("All image references resolve.")

# Anchor check using GitHub slug rules
def slug(h):
    h = re.sub(r"<[^>]+>", "", h).strip().lower()
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")

in_code = False
anchors = {}
for line in text.splitlines():
    if line.startswith("```"):
        in_code = not in_code
        continue
    if not in_code:
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            s = slug(m.group(2))
            n = anchors.get(s, -1) + 1
            anchors[s] = n
            if n:
                anchors[f"{s}-{n}"] = 0
links = set(re.findall(r"\]\(#([^)]+)\)", text))
broken = sorted(l for l in links if l not in anchors)
if broken:
    print("BROKEN ANCHORS:", broken)
else:
    print(f"All {len(links)} internal anchors resolve.")

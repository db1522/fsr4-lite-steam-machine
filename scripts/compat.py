# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Steam Machine Life
"""Builds compat.json, the plugin's snapshot of OptiScaler's community Compatibility List
(github.com/optiscaler/OptiScaler/wiki/Compatibility-List): each game's name, status and the upscaler inputs that
work, for the Now playing card. Run it before a release; nothing is downloaded while the plugin runs.

    python scripts/compat.py              downloads the list's Markdown from the wiki
    python scripts/compat.py --from FILE  reads a saved copy (Compatibility-List.md)

The table parsing is the Windows widget's CompatList.Parse. All credit to the OptiScaler community who keep the list."""
import datetime
import html
import json
import os
import re
import sys
import urllib.request

RAW_URL = "https://raw.githubusercontent.com/wiki/optiscaler/OptiScaler/Compatibility-List.md"
PAGE_URL = "https://github.com/optiscaler/OptiScaler/wiki/Compatibility-List"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "compat.json")


def plain(s):
    """A Markdown cell as readable text: links to their text, no backticks or bold, line breaks to spaces."""
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("**", "").replace("__", "").replace("`", "").replace("_", " ")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def status(cell):
    bad, good = "❌" in cell, "✅" in cell or "✔" in cell
    if bad and good:
        return "mixed"
    if bad:
        return "not_working"
    if "➖" in cell:
        return "partial"
    return "working"


def parse(markdown):
    """[[name, status, [inputs]], ...] from the list's main table (the first whose header starts "| Game |")."""
    lines = markdown.replace("\r", "").split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith("| Game |")), None)
    games = []
    if start is None:
        return games
    for line in lines[start + 2:]:
        line = line.strip()
        if line.startswith("#") or line.startswith("| Game |"):
            break
        if line.count("|") < 4:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        name = plain(cells[0])
        if not name or name.upper() == "GAME NAME":
            continue
        inputs = [x for x in (plain(p) for p in cells[2].split(",")) if x]
        games.append([name, status(cells[1]), inputs])
    return games


def main(argv):
    if len(argv) == 3 and argv[1] == "--from":
        with open(argv[2], encoding="utf-8") as f:
            text = f.read()
    elif len(argv) == 1:
        req = urllib.request.Request(RAW_URL, headers={"User-Agent": "fsr4-lite-steam-machine release script"})
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8")
    else:
        sys.exit(__doc__)
    games = parse(text)
    if len(games) < 50:
        sys.exit(f"Only {len(games)} games found: the list's layout may have changed. compat.json not written.")
    data = {"source": PAGE_URL, "date": datetime.date.today().isoformat(), "games": games}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"compat.json: {len(games)} games from the OptiScaler Compatibility List ({data['date']})")


if __name__ == "__main__":
    main(sys.argv)

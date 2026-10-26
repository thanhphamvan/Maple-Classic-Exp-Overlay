"""Makes the map-name list used by the overlay (assets/maps.txt) and the site (server/src/maps.js)
from a saved copy of https://meowdb.com/msclassic/maps/all (a fan-made MapleStory Classic database;
thank you to its makers). The list helps spell names the way the game does and tells towns from
hunting maps; it is not a gate: a name that isn't in it is still accepted.

  py -3 server/tools/make_maps.py <saved maps/all html page>

Run it again when the game adds maps."""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# meowdb marks a map "(town)" for more than cities and shops. Refusing a real hunting map would
# silently drop its runs, so these (which may have monsters, or are jump quests) are NOT treated
# as towns here even when it says so.
NOT_A_TOWN = re.compile(r"Florina Beach|Marr's Forest|Forgotten Hollow|Henesys Park|Pet-Walking Road|"
                        r"Forest of Patience|Thieves' Hideout|Top of the Hill|Maple Hill|Bygone Days|B2 <|Backalley")


# Maps the game has that meowdb's page doesn't (yet): new maps, event maps. Add "Name" or ("Name", is_town) here
# (see tools/moderation.sql, query 10), then run this again and deploy. They then show at once.
EXTRA_MAPS = []


def parse(page):
    names = {}
    for _, inner in re.findall(r'<a[^>]*href="/msclassic/maps/(\d+)"[^>]*>(.*?)</a>', page, re.S):
        text = html.unescape(re.sub(r"<[^>]+>", "|", inner))
        name = re.sub(r"\|.*", "", text).strip()
        if 3 <= len(name) <= 60:
            names.setdefault(name, set()).add("(town)" in text)
    # a name used by a town and a hunting map is treated as a hunting map
    for extra in EXTRA_MAPS:
        name, town = (extra, False) if isinstance(extra, str) else extra
        names[name] = {bool(town)}
    return sorted((n, int(flags == {True} and not NOT_A_TOWN.search(n))) for n, flags in names.items())


def main(path):
    maps = parse(Path(path).read_text(encoding="utf-8"))
    if len(maps) < 300:
        sys.exit(f"only {len(maps)} maps found: the page layout may have changed")
    (ROOT / "assets" / "maps.txt").write_text("".join(f"{n}\t{t}\n" for n, t in maps), encoding="utf-8", newline="\n")
    body = ",\n".join(f"  [{json.dumps(n, ensure_ascii=False)}, {t}]" for n, t in maps)
    (ROOT / "server" / "src" / "maps.js").write_text(
        "// Made by server/tools/make_maps.py from meowdb.com's map list. [name, 1 if it is a town].\n"
        f"export const MAPS = [\n{body},\n];\n", encoding="utf-8", newline="\n")
    print(f"{len(maps)} maps, {sum(t for _, t in maps)} of them towns")


if __name__ == "__main__":
    main(sys.argv[1])

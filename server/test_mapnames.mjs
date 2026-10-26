// Tests the map-name matching on its own (no server needed):  node server/test_mapnames.mjs
// Every map on the game's list must come back as itself, a misread must never turn into a
// DIFFERENT listed map, and odd input must be harmless.
import { canonicalMap, fixOrdinals, fixRomans, keyOf, tidy, LISTED } from "./src/mapnames.js";
import { MAPS } from "./src/maps.js";

let failures = 0;
const check = (name, ok, extra = "") => { console.log(`${ok ? "PASS" : "FAIL"} ${name}${extra ? ` (${extra})` : ""}`); failures += !ok; };

check("the list is loaded", LISTED > 300 && LISTED === MAPS.length, String(LISTED));

// every listed name is itself, and its town flag is the list's
let wrong = [];
for (const [name, town] of MAPS) {
  const c = canonicalMap(name);
  if (!c.listed || c.name !== tidy(name) || c.town !== !!town) wrong.push(name);
}
check("every map on the list comes back as itself", wrong.length === 0, wrong.slice(0, 3).join("; "));

// misreads: one slip must give the same map, or be left alone, never another listed map
const slips = [
  (s, i) => s.slice(0, i) + s.slice(i + 1),                                   // a dropped letter
  (s, i) => s.slice(0, i) + (s[i] === "I" ? "l" : s[i] === "l" ? "I" : s[i]) + s.slice(i + 1),   // I <-> l
  (s, i) => s.slice(0, i) + (s[i] === "o" ? "0" : s[i]) + s.slice(i + 1),     // o -> 0
  (s, i) => s.slice(0, i) + s[i] + s[i] + s.slice(i + 1),                     // a doubled letter
];
let snapped = 0, kept = 0, crossed = [];
for (const [name] of MAPS) {
  const own = canonicalMap(name);
  const clean = tidy(name);
  for (const slip of slips) {
    for (const i of [1, Math.floor(clean.length / 2), clean.length - 2]) {
      const bad = slip(clean, i);
      if (bad === clean) continue;
      const c = canonicalMap(bad);
      if (c.listed && c.name === tidy(bad)) continue;                       // it IS another map's real name (Ant Tunnel II minus an I)
      if (c.listed && c.name !== own.name) crossed.push(`${bad} -> ${c.name}`);
      c.listed ? snapped++ : kept++;
    }
  }
}
check("a misread never turns into a DIFFERENT listed map", crossed.length === 0, crossed.slice(0, 3).join("; "));
console.log(`     (${snapped} slips put right, ${kept} left as read)`);

// the cases people have actually seen
const cases = {
  "ist Accompaniment Bonus": "1st Accompaniment Bonus", "Ist Accompaniment Bonus": "1st Accompaniment Bonus",
  "The Land of Wild Boar Il": "The Land of Wild Boar II", "Tree Dungeon Monkey Forest II": "Tree Dungeon, Monkey Forest II",
  "Rocky Road lI": "Rocky Road II", "Ant Tunnel l": "Ant Tunnel I",
};
for (const [read, want] of Object.entries(cases)) check(`"${read}" is "${want}"`, canonicalMap(read).name === want);
check("different Roman numerals stay different maps", canonicalMap("Ant Tunnel II").name === "Ant Tunnel II" && canonicalMap("Ant Tunnel I").name === "Ant Tunnel I");
check("Free Market 11 isn't turned into Free Market II", canonicalMap("Free Market 11").name === "Free Market 11");
check("towns are towns", ["Perion", "Henesys", "Ellinia", "Kerning City", "Free Market 3"].every((n) => canonicalMap(n).town));
check("...hunting maps that share a town's name aren't", !canonicalMap("Henesys Hunting Ground II").town && !canonicalMap("Perion Street Corner").town);
check("...and maps meowdb marks but may have monsters aren't refused", !canonicalMap("Florina Beach").town && !canonicalMap("Henesys Park").town);
check("an unknown name is kept (an event map)", JSON.stringify(canonicalMap("Halloween Event Field")) === JSON.stringify({ name: "Halloween Event Field", town: false, listed: false, junk: false }));

// the Roman numerals seen misread in real data, and menus read as maps
const romans = {
  "Tree Dungeon Forest Up North Vil": "Tree Dungeon, Forest Up North VII", "Tree Dungeon Forest Up North Vill": "Tree Dungeon, Forest Up North VIII",
  "Ant Tunnel lV": "Ant Tunnel IV", "Ant Tunnel il": "Ant Tunnel II", "Ant Tunnel ill": "Ant Tunnel III", "Rocky Road iil": "Rocky Road III",
  "East Rocky Mountain Vil": "East Rocky Mountain VII", "East Rocky Mountain il": "East Rocky Mountain II",
  "The Forest of Evil il": "The Forest of Evil II", "Tree Dungeon Forest Up North V1": "Tree Dungeon, Forest Up North VI",
};
for (const [read, want] of Object.entries(romans)) check(`"${read}" is "${want}"`, canonicalMap(read).name === want, canonicalMap(read).name);
check("a plain number isn't a numeral", fixRomans("Free Market 11") === "Free Market 11" && fixRomans("Maps 5") === "Maps 5" && fixRomans("Hall 1") === "Hall 1");
check("an ordinary last word isn't a numeral", fixRomans("Mill") === "Mill" && fixRomans("Big Ill Town") === "Big Ill Town" && fixRomans("Sky Vixen") === "Sky Vixen");
check("an impossible numeral is left alone", fixRomans("Cave IIIII") === "Cave IIIII" && fixRomans("Cave VX") === "Cave VX");
const junks = ["Se ee", "oe ee", "WORLD", "Hidden Street", "I Use I SetUp te Cash Deco", "Keyboard Mouse Controller", "I I", "e o", "Jee sce", "y I Party I Blacklist", "CITIZENS HIE ITEM"];
check("menus and scraps of text are not maps", junks.every((n) => canonicalMap(tidy(n)).junk), junks.filter((n) => !canonicalMap(tidy(n)).junk).join("; "));
const real = ["Ant Tunnel", "Deep Ant Tunnel", "The Burnt Land", "Halloween Event Field", "Rocky Road II", "Sleepywood Dungeon", "Free Market <3>"];
check("real and plausible names are not junk", real.every((n) => !canonicalMap(tidy(n)).junk), real.filter((n) => canonicalMap(tidy(n)).junk).join("; "));
check("every map on the list is not junk", MAPS.every(([n]) => !canonicalMap(n).junk));

// odd input is harmless
const odd = ["", " ", "   ", "<script>alert(1)</script>", "constructor", "__proto__", "toString", "x".repeat(300), "😀😀😀", "\u0000\u0001", "I".repeat(200), "ist ".repeat(50)];
let threw = null;
for (const o of odd) { try { const c = canonicalMap(tidy(o)); if (typeof c.name !== "string") threw = o; } catch (e) { threw = `${o}: ${e}`; } }
check("odd input never throws", threw === null, String(threw));
check("angle brackets can't survive tidy()", !/[<>]/.test(canonicalMap(tidy("<b>Bold</b> Map")).name));
const a = canonicalMap("Perion"); a.name = "changed";
check("the answer can't be changed for the next caller", canonicalMap("Perion").name === "Perion");
check("ordinals: only whole words are fixed", fixOrdinals("Mist Island") === "Mist Island" && fixOrdinals("ist Hall") === "1st Hall");
check("roman numerals: a plain number is left alone", fixRomans("Free Market 11") === "Free Market 11" && fixRomans("Boar Il") === "Boar II");

const t0 = performance.now();
for (let i = 0; i < 400; i++) canonicalMap(`Unlisted Event Place ${i} Of Fun`);
const each = (performance.now() - t0) / 400;
check(`an unlisted name costs under 1 ms (${each.toFixed(2)} ms)`, each < 1);
check("keys ignore punctuation and case", keyOf("Tree Dungeon, Monkey Forest II") === keyOf("tree dungeon monkey forest ii"));

console.log(failures ? `\n${failures} FAILED` : "\nALL PASSED");
process.exit(failures ? 1 : 0);

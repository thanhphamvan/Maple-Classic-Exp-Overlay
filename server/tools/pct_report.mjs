// How much of a level an hour real runs gain, by level, to check the limits in src/index.js (PCT_CAPS) are well above
// what real players get. Read-only. Make the file, then run this:
//
//   node_modules\.bin\wrangler d1 execute classicexp --remote --json --command "SELECT level_start, level_end, exp_hr FROM runs WHERE level_start >= 30" > tools/runs-live.json
//   node tools/pct_report.mjs tools/runs-live.json
import fs from "node:fs";
import { pctPerHour } from "../src/index.js";

const bytes = fs.readFileSync(process.argv[2]);
let text = bytes[0] === 0xff && bytes[1] === 0xfe ? bytes.toString("utf16le") : bytes.toString("utf8");
text = text.replace(/^\uFEFF/, "");
const rows = JSON.parse(text.slice(text.search(/^\s*[\[{]/m)))[0].results;
if (!rows.length || rows[0].exp_hr === undefined) throw new Error("no runs in this file: make it with --command, as above");
const bands = new Map();
for (const r of rows) {
  const pct = pctPerHour(r);
  if (pct === null || !Number.isFinite(pct)) continue;
  const band = Math.floor(r.level_start / 10) * 10;
  if (!bands.has(band)) bands.set(band, []);
  bands.get(band).push(pct);
}
const q = (v, p) => v[Math.min(v.length - 1, Math.floor((v.length - 1) * p))];
console.log("levels   runs   median   p99     highest   (% of a level per hour)");
for (const band of [...bands.keys()].sort((a, b) => a - b)) {
  const v = bands.get(band).sort((a, b) => a - b);
  console.log(`${band}-${band + 9}`.padEnd(9), String(v.length).padEnd(6), q(v, 0.5).toFixed(1).padEnd(8), q(v, 0.99).toFixed(1).padEnd(7), v.at(-1).toFixed(1));
}
console.log("\nThe limits now: from Lv 30 300, from 60 200, from 100 150, from 150 100. A band whose 'highest' is close to its limit means the limit is too tight.");

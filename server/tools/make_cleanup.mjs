// Writes the SQL that puts the maps already in the database right, with the same rules the site
// now applies to every new run (src/mapnames.js): OCR slips fixed ("ist" -> "1st"), the game's
// spelling used, and runs on towns taken out (nobody farms in a town).
//
//   node tools/make_cleanup.mjs tools/maps-live.json tools/cleanup-maps.sql
//
// It only prints SQL; nothing is changed until the SQL is run, which is up to you:
//   npx wrangler d1 execute classicexp --remote --file tools/cleanup-maps.sql --yes
//   npx wrangler d1 execute classicexp --remote --file schema.sql --yes     (rebuilds the summary tables)
import fs from "node:fs";
import { canonicalMap } from "../src/mapnames.js";

/** The report's JSON, whatever way it was saved: PowerShell's ">" writes UTF-16 with a marker, and
 * wrangler may print a line or two of text before the JSON. */
function readReport(file) {
  const bytes = fs.readFileSync(file);
  let text = bytes[0] === 0xff && bytes[1] === 0xfe ? bytes.toString("utf16le")
    : bytes[0] === 0xfe && bytes[1] === 0xff ? Buffer.from(bytes.subarray(2)).swap16().toString("utf16le") : bytes.toString("utf8");
  text = text.replace(/^﻿/, "");
  const start = text.search(/^\s*[\[{]/m);                          // the first line that starts the JSON
  if (start < 0) throw new Error(`no JSON in ${file}: did the report command fail?`);
  return JSON.parse(text.slice(start));
}

const raw = readReport(process.argv[2]);
const rows = (Array.isArray(raw) ? raw[0] : raw).results;
if (!Array.isArray(rows) || rows.length === 0 || typeof rows[0].map !== "string") {
  throw new Error("this file has no map names in it. Make it with --command (not --file), as in the header of tools/map_report.sql.");
}
const q = (s) => `'${String(s).replace(/'/g, "''")}'`;
const out = ["-- Made by tools/make_cleanup.mjs. Review it, then run it."];
const review = [];
let renames = 0, towns = 0, junked = 0;
for (const { map, players, runs } of rows) {
  const c = canonicalMap(map);
  if (c.town) {
    out.push(`-- town: ${map} (${players} players, ${runs} runs)`, `DELETE FROM runs WHERE map = ${q(map)};`);
    towns++;
  } else if (c.junk) {
    out.push(`-- not a map (a menu or a misread): ${map} (${players} players, ${runs} runs)`, `DELETE FROM runs WHERE map = ${q(map)};`);
    junked++;
  } else if (c.name !== map) {
    out.push(`-- ${map}  ->  ${c.name}  (${players} players, ${runs} runs)`);
    // (runs of one player can't collide: a run is unique by player and start time)
    out.push(`UPDATE OR IGNORE runs SET map = ${q(c.name)} WHERE map = ${q(map)};`, `DELETE FROM runs WHERE map = ${q(map)};`);
    renames++;
  } else if (!c.listed) {
    review.push(`--   ${map} (${players} players, ${runs} runs)`);
  }
}
out.push("DELETE FROM answers;", "",
  `-- ${renames} names put right, ${towns} town names and ${junked} not-a-map names removed.`,
  "-- Not on the game's list (event maps, new maps, or misreads): left as they are. Look them over:", ...review);
const sql = out.join("\n") + "\n";
if (process.argv[3]) {
  fs.writeFileSync(process.argv[3], sql, "utf8");                  // plain UTF-8, which wrangler reads
  console.log(`${renames} names put right, ${towns} town names and ${junked} not-a-map names removed. Written to ${process.argv[3]}: open it and read it before running it.`);
} else {
  console.log(sql);
}

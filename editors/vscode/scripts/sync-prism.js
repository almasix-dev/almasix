#!/usr/bin/env node
/** Copy Prism grammar assets from editors/prism into this extension. */
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const prism = path.resolve(root, "..", "prism");

const copies = [
  ["syntaxes/prism.tmLanguage.json", "syntaxes/prism.tmLanguage.json"],
  ["language-configuration.json", "language-configuration.json"],
  ["snippets/prism.code-snippets", "snippets/prism.code-snippets"],
];

for (const [fromRel, toRel] of copies) {
  const from = path.join(prism, fromRel);
  const to = path.join(root, toRel);
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
  console.log(`synced ${fromRel} -> ${toRel}`);
}

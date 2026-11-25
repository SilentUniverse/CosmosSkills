#!/usr/bin/env node
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const PELE_VERSION = "1.9.0";
const CSS = `.pele{--pele-bg:#ffffff;--pele-fg:#1c1c1c;--pele-muted:#656565;--pele-line:#808080;--pele-surface:#fcfcfc;--pele-surface-alt:#f1f1f1;--pele-border:#c9c9c9}
.pele .blue rect{fill:#c3e0ff}.pele .orange rect{fill:#f0d3bf}.pele .purple rect{fill:#e3d5ff}.pele .yellow rect{fill:#f0dcbf}
.pele .teal rect{fill:#bfe3df}.pele .tan rect{fill:#e5d9ce}.pele .pink rect{fill:#ffcbe6}
.pele .breaks rect{fill:#ffecee !important;stroke:#e72e3b !important;stroke-width:2.5px !important}.pele .breaks text{fill:#cd2834 !important}
.pele .mayBreak rect{fill:#fff3e6 !important;stroke:#e8730c !important;stroke-width:2.5px !important}.pele .mayBreak text{fill:#b85a06 !important}
.pele .bugPath rect{stroke:#1680f3 !important;stroke-width:2.5px !important}
.pele .repeats rect{stroke:#9b35d6 !important;stroke-width:2.5px !important;stroke-dasharray:6 3}
@media (prefers-color-scheme:dark){.pele{--pele-bg:#1f1f1f;--pele-fg:#f5f5f5;--pele-muted:#acacac;--pele-line:#939393;--pele-surface:#121212;--pele-surface-alt:#2c2c2c;--pele-border:#4e4e4e}
.pele .blue rect{fill:#1b3857}.pele .orange rect{fill:#573117}.pele .purple rect{fill:#3c2e57}.pele .yellow rect{fill:#573d17}
.pele .teal rect{fill:#174641}.pele .tan rect{fill:#3d3127}.pele .pink rect{fill:#57233e}
.pele .breaks rect{fill:#2e2021 !important;stroke:#cf2b35 !important}.pele .breaks text{fill:#ff6463 !important}
.pele .mayBreak rect{fill:#2e2619 !important;stroke:#d0700f !important}.pele .mayBreak text{fill:#ffa257 !important}
.pele .bugPath rect{stroke:#116dd2 !important}.pele .repeats rect{stroke:#9a3fcf !important}}`;

function usage(message) {
  if (message) console.error(message);
  console.error("usage: render.mjs CHART.mmd [--out FILE.svg]");
  process.exit(2);
}

export function sourceDigest(text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n").map((line) => line.trimEnd()).filter(Boolean);
  return createHash("sha256").update(lines.join("\n"), "utf8").digest("hex");
}

async function loadPele() {
  const cache = process.env.XDG_CACHE_HOME || path.join(os.homedir(), ".cache");
  const dir = process.env.PELE_DIR || path.join(cache, "cosmos", "pele", PELE_VERSION);
  const manifest = path.join(dir, "node_modules", "pele", "package.json");
  if (!existsSync(manifest)) {
    console.error(`installing pele@${PELE_VERSION} into ${dir} (needs network once)`);
    execFileSync("npm", ["install", "--prefix", dir, "--no-audit", "--no-fund", `pele@${PELE_VERSION}`],
                 { stdio: ["ignore", "ignore", "inherit"] });
  }
  const version = JSON.parse(readFileSync(manifest, "utf8")).version;
  if (version !== PELE_VERSION) usage(`pele ${version} at ${dir}; expected ${PELE_VERSION}`);
  const entry = createRequire(path.join(dir, "noop.js")).resolve("pele");
  return import(pathToFileURL(entry).href);
}

async function main(argv) {
  const input = argv[0];
  if (!input || input.startsWith("-")) usage();
  let out = input.replace(/\.mmd$/, "") + ".svg";
  for (let i = 1; i < argv.length; i += 2) {
    if (argv[i] !== "--out" || !argv[i + 1]) usage(`unknown argument ${argv[i]}`);
    out = argv[i + 1];
  }
  const source = readFileSync(input, "utf8");
  const { render, PeleError } = await loadPele();
  let svg;
  try {
    ({ svg } = render(source, { limit: 1_000_000, outputLimit: 8_000_000, maxEdges: 10_000 }));
  } catch (error) {
    if (!(error instanceof PeleError)) throw error;
    console.error(error.message);
    process.exit(1);
  }
  const open = svg.indexOf(">", svg.indexOf("<svg")) + 1;
  const stamp = `<!-- statechart-source sha256:${sourceDigest(source)} --><style>${CSS}</style>`;
  writeFileSync(out, svg.slice(0, open) + stamp + svg.slice(open));
  console.log(out);
}

await main(process.argv.slice(2));

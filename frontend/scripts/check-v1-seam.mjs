#!/usr/bin/env node
/*
 * Seam guard for the frontend v1 epic (P0-T10). Until Phase 9, v1 work may
 * change v0 only at the seam: the files in scripts/v1-seam-allowlist.json.
 *
 * A change set is v1 work when it touches src/v1/ or the v1 tooling
 * (scripts/*v1*, test-fixtures/v1-*, and top-level files such as
 * vitest.v1.config.mts). Anything else is v0 work, such as a v0 bug fix, and
 * passes untouched: the seam limits the epic, not v0.
 *
 * "v0" here is the code that ships as v0: src/ outside src/v1/, public/, and
 * index.html, v0's HTML shell. Build, test and CI configuration
 * (package.json, vite.config.js, biome.json, scripts/, test-fixtures/, docs/,
 * ...) sits outside both and is never guarded, and so do nginx.conf and
 * default.conf: they serve v0 and v1 alike and are reviewed as deployment
 * configuration. A deleted or renamed v0 file counts as a change to it.
 *
 * With --base, the allowlist is read from the base branch, so a PR cannot
 * widen the seam and pass in the same change: a wider allowlist applies from
 * the next PR, once it is reviewed and merged. Only when the base has no
 * allowlist yet (the guard's own introduction) is the PR's copy used.
 *
 *   --base <ref>      Changed files are `git diff <ref>...HEAD` (CI passes the
 *                     PR's base branch).
 *   --changed <file>  Changed files are read from <file>, one path per line,
 *                     relative to frontend/ (used by the fixtures).
 *   --override        Report the files, then pass. CI sets it when the PR
 *                     carries the `v0-change` label: v1 work that genuinely
 *                     needs a v0 change, made visible to reviewers by the
 *                     label.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const FRONTEND = path.join(import.meta.dirname, "..");
const ALLOWLIST_REL = "scripts/v1-seam-allowlist.json";
const GUARDED = [/^src\/(?!v1\/)/, /^public\//, /^index\.html$/];
const V1_WORK = [
  /^src\/v1\//,
  /^[^/]*v1[^/]*$/,
  /^scripts\/[^/]*v1[^/]*$/,
  /^test-fixtures\/v1-[^/]+\//,
];

function usage(message) {
  console.error(`check-v1-seam: ${message}`);
  console.error(
    "usage: check-v1-seam.mjs (--base <ref> | --changed <file>) [--override]",
  );
  process.exit(2);
}

function parseArgs(argv) {
  const opts = { base: null, changed: null, override: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--override") {
      opts.override = true;
    } else if (arg === "--base" || arg === "--changed") {
      const value = argv[i + 1];
      if (!value || value.startsWith("--")) {
        usage(`${arg} needs a value`);
      }
      opts[arg.slice(2)] = value;
      i += 1;
    } else {
      usage(`unknown argument '${arg}'`);
    }
  }
  if (Boolean(opts.base) === Boolean(opts.changed)) {
    usage("pass exactly one of --base and --changed");
  }
  return opts;
}

/* `**` crosses folders, `*` and `?` stay inside one; nothing else is special. */
function globToRegExp(glob) {
  let source = "";
  for (let i = 0; i < glob.length; i += 1) {
    const ch = glob[i];
    if (ch === "*" && glob[i + 1] === "*") {
      // `**/` also matches no folder at all.
      if (glob[i + 2] === "/") {
        source += "(?:.*/)?";
        i += 2;
      } else {
        source += ".*";
        i += 1;
      }
    } else if (ch === "*") {
      source += "[^/]*";
    } else if (ch === "?") {
      source += "[^/]";
    } else {
      source += ch.replace(/[.+^${}()|[\]\\]/g, String.raw`\$&`);
    }
  }
  return new RegExp(`^${source}$`);
}

/* git from PATH on purpose: a developer/CI tool with no fixed location
 * across macOS and Linux (as in the boundary fixtures). */
function git(args) {
  const options = { cwd: FRONTEND, encoding: "utf8" };
  return spawnSync("git", args, options); // NOSONAR
}

/* The allowlist's text: from the base branch with --base, else the file. */
function allowlistSource(base) {
  if (base) {
    const shown = git(["show", `${base}:./${ALLOWLIST_REL}`]);
    if (!shown.error && shown.status === 0) {
      return { text: shown.stdout, from: `${base}:${ALLOWLIST_REL}` };
    }
  }
  const file = path.join(FRONTEND, ALLOWLIST_REL);
  try {
    return { text: fs.readFileSync(file, "utf8"), from: ALLOWLIST_REL };
  } catch (error) {
    console.error(`check-v1-seam: cannot read ${file}: ${error.message}`);
    process.exit(2);
  }
}

function readAllowlist(base) {
  const { text, from } = allowlistSource(base);
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    console.error(`check-v1-seam: cannot parse ${from}: ${error.message}`);
    process.exit(2);
  }
  if (
    !Array.isArray(parsed.allow) ||
    parsed.allow.some((glob) => typeof glob !== "string" || glob === "")
  ) {
    console.error(`check-v1-seam: ${from} needs an "allow" list of globs`);
    process.exit(2);
  }
  return parsed.allow.map((glob) => ({ glob, re: globToRegExp(glob) }));
}

function changedFromGit(base) {
  // -z: paths NUL-separated and never quoted, so a non-ASCII path such as
  // src/pages/Überblick.jsx is matched as written.
  const args = ["diff", "--name-only", "-z", "--no-renames", "--relative"];
  args.push(`${base}...HEAD`, "--", ".");
  const result = git(args);
  if (result.error || result.status !== 0) {
    console.error(
      `check-v1-seam: git diff against '${base}' failed: ${result.error?.message ?? result.stderr.trim()}`,
    );
    process.exit(2);
  }
  return result.stdout.split("\0");
}

function changedFromFile(file) {
  try {
    return fs.readFileSync(file, "utf8").split("\n");
  } catch (error) {
    console.error(`check-v1-seam: cannot read ${file}: ${error.message}`);
    process.exit(2);
  }
}

const opts = parseArgs(process.argv.slice(2));
const allow = readAllowlist(opts.base);
const changed = (
  opts.base ? changedFromGit(opts.base) : changedFromFile(opts.changed)
)
  .map((line) => line.trim().replace(/^\.\//, ""))
  .filter(Boolean);

if (!changed.some((file) => V1_WORK.some((re) => re.test(file)))) {
  console.log(
    `check-v1-seam: ok (${changed.length} changed file(s), none of them v1 work)`,
  );
  process.exit(0);
}

const outside = changed.filter(
  (file) =>
    GUARDED.some((re) => re.test(file)) &&
    !allow.some(({ re }) => re.test(file)),
);

if (outside.length === 0) {
  console.log(
    `check-v1-seam: ok (${changed.length} changed file(s), none in v0 outside the seam)`,
  );
  process.exit(0);
}

const lines = outside.map(
  (file) =>
    `frontend/${file}: changes v0 outside the seam allowlist (scripts/v1-seam-allowlist.json).`,
);
if (opts.override) {
  console.log(lines.join("\n"));
  console.log(
    `\ncheck-v1-seam: ${outside.length} v0 file(s) changed; passing because the PR is labelled v0-change.`,
  );
  process.exit(0);
}
console.error(lines.join("\n"));
console.error(
  `\ncheck-v1-seam: ${outside.length} v0 file(s) outside the seam. v1 work changes v0 only at the seam; if this v1 work genuinely needs the v0 change, label the PR v0-change.`,
);
process.exit(1);

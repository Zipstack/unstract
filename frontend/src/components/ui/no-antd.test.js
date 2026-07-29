import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * antd is gone. This keeps it gone.
 *
 * A one-time grep proves today's tree is clean; it does nothing about the next
 * dependency bump. antd survived the entire migration as a TRANSITIVE
 * dependency — every plan task about removing it checked source imports and
 * `package.json`, and all of them passed while a 58MB copy of antd sat in
 * node_modules because `react-js-cron` depended on it. Nothing failed, so
 * nothing surfaced it.
 *
 * These checks cover all three ways it can come back: a direct dependency, a
 * transitive one, and a stray import.
 */

const FRONTEND = path.resolve(import.meta.dirname, "../../..");
const BANNED = [/^antd$/, /^@ant-design\//];

function readJson(file) {
  return JSON.parse(fs.readFileSync(path.join(FRONTEND, file), "utf8"));
}

describe("antd must not return", () => {
  it("is not a declared dependency", () => {
    const pkg = readJson("package.json");
    const declared = [
      ...Object.keys(pkg.dependencies ?? {}),
      ...Object.keys(pkg.devDependencies ?? {}),
    ];
    const offenders = declared.filter((name) =>
      BANNED.some((re) => re.test(name)),
    );
    expect(
      offenders,
      `These are declared in package.json: ${offenders.join(", ")}`,
    ).toEqual([]);
  });

  /**
   * The one that actually caught it. `react-js-cron` never appeared in any
   * source file's imports, so only the resolved tree revealed antd.
   */
  it("is not reachable transitively", () => {
    const lock = fs.readFileSync(path.join(FRONTEND, "bun.lock"), "utf8");
    // Lockfile entries are quoted package specifiers, e.g. "antd" or
    // "@ant-design/icons". Match the key form so a substring like
    // "antd-overlays" in a path cannot produce a false positive.
    const hits = [...lock.matchAll(/"(antd|@ant-design\/[^"@]+)"\s*:/g)].map(
      (m) => m[1],
    );
    expect(
      [...new Set(hits)],
      "antd is back in the resolved dependency tree. Something depends on it — " +
        "run `npm ls antd` to find what.",
    ).toEqual([]);
  });

  it("is not imported anywhere in src", () => {
    const offenders = [];
    const walk = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name === "node_modules") {
            continue;
          }
          walk(full);
          continue;
        }
        if (!/\.(jsx?|tsx?)$/.test(entry.name)) {
          continue;
        }
        // Strip comments first — otherwise a doc comment naming the banned
        // import counts as a call-site, including this file's own.
        const src = fs
          .readFileSync(full, "utf8")
          .replace(/\/\*[\s\S]*?\*\//g, "")
          .replace(/^\s*\/\/.*$/gm, "");
        // Real imports only. Our own `@/components/ui/shims/antd-*` shims keep the
        // antd NAME deliberately while running on shadcn, so they must not
        // match: the pattern anchors on the exact specifier.
        if (/from\s+["']antd["']|from\s+["']@ant-design\//.test(src)) {
          offenders.push(path.relative(FRONTEND, full));
        }
      }
    };
    walk(path.join(FRONTEND, "src"));
    expect(
      offenders,
      `These import antd directly:\n  ${offenders.join("\n  ")}`,
    ).toEqual([]);
  });
});

#!/usr/bin/env node
/*
 * Separation guard for the frontend v1 epic (P0-T10): the public repository's
 * v1 tree holds no enterprise plugin code.
 *
 * Cloud v1 plugins live in unstract-cloud and are copied into
 * src/v1/plugins/<id>/ at build time (spec decision D7). The public tree keeps
 * only the plugin registry's own top-level files there, so any folder under
 * src/v1/plugins/ is an overlaid plugin.
 *
 * Inside a git work tree only tracked files count, so a developer with the
 * cloud overlay copied in (ignored by .gitignore) still passes; what fails is
 * a plugin that was committed. Outside git (the fixtures) the folder itself
 * is read.
 *
 * The other half of the guard, that v1 builds, lints and passes its tests
 * with no overlay present, is the v1 CI jobs themselves: they run on a clean
 * checkout of this repository, which has no overlay.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const FRONTEND = path.join(import.meta.dirname, "..");
const PLUGINS_REL = "src/v1/plugins";
const PLUGINS = path.join(FRONTEND, PLUGINS_REL);

function trackedPluginPaths() {
  // Paths come back relative to the working directory, i.e. frontend/.
  const result = spawnSync("git", ["ls-files", "--", PLUGINS_REL], {
    cwd: FRONTEND,
    encoding: "utf8",
  });
  if (result.error || result.status !== 0) {
    return null;
  }
  return result.stdout
    .split("\n")
    .filter(Boolean)
    .map((file) => file.slice(PLUGINS_REL.length + 1));
}

function diskPluginPaths() {
  if (!fs.existsSync(PLUGINS)) {
    return [];
  }
  return fs
    .readdirSync(PLUGINS, { recursive: true, withFileTypes: true })
    .filter((entry) => !entry.isDirectory())
    .map((entry) =>
      path
        .relative(PLUGINS, path.join(entry.parentPath, entry.name))
        .split(path.sep)
        .join("/"),
    );
}

const insideGit =
  spawnSync("git", ["rev-parse", "--is-inside-work-tree"], {
    cwd: FRONTEND,
    encoding: "utf8",
  }).stdout.trim() === "true";
const files = (insideGit && trackedPluginPaths()) || diskPluginPaths();

const plugins = [
  ...new Set(
    files
      .filter((file) => file.includes("/"))
      .map((file) => file.split("/")[0]),
  ),
].sort();

if (plugins.length === 0) {
  console.log("check-v1-separation: ok");
  process.exit(0);
}
console.error(
  plugins
    .map(
      (id) =>
        `${PLUGINS_REL}/${id}/: enterprise plugin code in the public repository. Cloud v1 plugins live in unstract-cloud and are copied in at build time (spec D7).`,
    )
    .join("\n"),
);
console.error(`\ncheck-v1-separation: ${plugins.length} plugin folder(s).`);
process.exit(1);

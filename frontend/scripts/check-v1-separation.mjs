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
 * The other half of the guard, that v1 typechecks, lints and passes its
 * tests with no overlay present, is the v1 CI jobs themselves: they run on a
 * clean checkout of this repository, which has no overlay. The production
 * build covers v1 only once v0 imports it (the version switch, P0-T03);
 * until then a v1 file nothing imports is not built.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const FRONTEND = path.join(import.meta.dirname, "..");
const PLUGINS_REL = "src/v1/plugins";
const PLUGINS = path.join(FRONTEND, PLUGINS_REL);

/* git from PATH on purpose: a developer/CI tool with no fixed location
 * across macOS and Linux (as in the boundary fixtures). */
function git(args) {
  const options = { cwd: FRONTEND, encoding: "utf8" };
  return spawnSync("git", args, options); // NOSONAR
}

function trackedPluginPaths() {
  // Paths come back relative to the working directory, i.e. frontend/, and
  // with -z unquoted, so a non-ASCII name is read as written.
  const result = git(["ls-files", "-z", "--", PLUGINS_REL]);
  if (result.error || result.status !== 0) {
    return null;
  }
  return result.stdout
    .split("\0")
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
  git(["rev-parse", "--is-inside-work-tree"]).stdout?.trim() === "true";
const files = (insideGit && trackedPluginPaths()) || diskPluginPaths();

const plugins = [
  ...new Set(
    files
      .filter((file) => file.includes("/"))
      .map((file) => file.split("/")[0]),
  ),
].sort((a, b) => a.localeCompare(b));

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

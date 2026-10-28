#!/usr/bin/env node
/*
 * Styling policy for the v1 frontend (src/v1/). Run by `lint:v1` after
 * check-v1.mjs; the rules and their reasons are in src/v1/README.md.
 *
 *   S1  No inline style (JSX `style=`).
 *   S2  No raw colour: hex, rgb()/hsl()/oklch()/oklab()/color(), or a
 *       Tailwind palette utility (`-red-500`, `-white`).
 *   S3  No raw pixel value: `[13px]` arbitrary values, or px/rem/em/pt in CSS.
 *   S4  No !important: a `!` class modifier, or `!important` in CSS.
 *   S5  CSS is imported only from app/ and styles/.
 *   S6  Every CSS selector starts with `.v1`, except inside @theme, @utility,
 *       @custom-variant, @font-face and @keyframes.
 *   S7  CSS never reads prefers-color-scheme; data-theme sets the mode.
 *   S8  Every Tailwind utility carries the `ui:` prefix. v0's stylesheet also
 *       scans src/v1, so an unprefixed class would render with v0's theme.
 *
 * In TypeScript, S2 to S4 and S8 read only the contents of string and template
 * literals, so a non-null `!` or a hex-looking identifier never matches. Test
 * files and styles/tokens.ts (the raw values, by design) are skipped for them.
 * In CSS, comments are blanked first; the generated styles/tokens.css is
 * skipped for S2 and S3 only.
 *
 * S8 checks a list of utility stems, not a Tailwind parse: a missing stem is a
 * false negative. A bare stem counts only when it is a whole utility (`flex`),
 * so a string such as "font" or "top" is not flagged.
 *
 * blankComments and its helpers are copied from check-v1.mjs, which runs on
 * import and so cannot be imported; keep the two in step.
 *
 * It always checks the src/v1 beside this script, like
 * check-v1.mjs; the fixtures in test-fixtures/v1-boundary/ rely on that.
 */
import fs from "node:fs";
import path from "node:path";

const ROOT = path.join(import.meta.dirname, "..", "src", "v1");

const CODE_EXT = /\.(ts|tsx|mts|cts)$/;
const CSS_EXT = /\.css$/;
const TEST_FILE = /\.(test|spec)\.(ts|tsx|mts|cts)$/;
const RAW_VALUES_TS = "styles/tokens.ts";
const GENERATED_CSS = "styles/tokens.css";
// Folders whose files may import a .css file.
const CSS_IMPORTERS = new Set(["app", "styles"]);

const MSG = {
  inlineStyle: "No inline style under v1; style with tokens and Tailwind.",
  colour: "No raw colour under v1; use a token from styles/tokens.ts.",
  pixel: "No raw pixel value under v1; use a token or the spacing scale.",
  important: "No !important under v1.",
  cssImport: "CSS is imported only from app/ and styles/ under v1.",
  unscoped: "Every v1 selector is scoped to .v1.",
  colourScheme:
    "v1 never reads prefers-color-scheme in CSS; mode comes from data-theme.",
  unprefixed:
    "No unprefixed Tailwind utility under v1; write ui:<utility>. v0's stylesheet also scans src/v1, so an unprefixed class would render with v0's theme.",
};

const PALETTE =
  "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const RAW_COLOUR_RES = [
  /#[0-9a-fA-F]{3,8}(?![\w-])/g,
  /(?<![\w-])(?:rgba?|hsla?|oklch|oklab|color)\(/g,
  new RegExp(String.raw`-(?:${PALETTE})-\d{2,3}(?![\w-])`, "g"),
  /-(?:white|black)(?![\w-])/g,
];
// A Tailwind arbitrary value in a unit: `w-[13px]`, `p-[1.5rem]`.
const ARBITRARY_UNIT_RE = /\[[^\]\s]*\d(?:px|rem|em|pt)\]/g;
// A CSS length in a unit: `3px`, `.5rem`, `-1em`.
const CSS_UNIT_RE = /(?<![\w.])(?:\d+\.?\d*|\.\d+)(?:px|rem|em|pt)(?![\w-])/g;
const CSS_IMPORTANT_RE = /!\s*important\b/g;
const COLOUR_SCHEME_RE = /prefers-color-scheme/g;
const INLINE_STYLE_RE = /(?<![\w-])style\s*=\s*[{"']/g;

// Stems that are a complete utility on their own, so a bare `flex` counts.
const WHOLE_STEMS = [
  "flex grid block inline hidden absolute relative fixed sticky truncate",
  "sr-only border shadow ring outline transition",
];
// Stems that are a utility only with a value after a `-`: `font-sans`, not `font`.
const PREFIX_STEMS = [
  "bg text rounded p px py pt pr pb pl m mx my mt mr mb ml gap w h min-w",
  "min-h max-w max-h size items justify font leading tracking z inset top",
  "left right bottom overflow opacity duration cursor select space",
];
const stems = (lines) =>
  lines
    .join(" ")
    .split(" ")
    .map((s) => s.replace("-", "\\-"))
    .join("|");
// A leading `-` is a negative value (`-mt-2`); a trailing `!` is important.
const UTILITY_RE = new RegExp(
  `^-?(?:(?:${stems(WHOLE_STEMS)})(?:-|!?$)|(?:${stems(PREFIX_STEMS)})-)`,
);
// One leading variant: `hover:`, `md:`, `data-[state=open]:`, `[&>*]:`.
const VARIANT_RE = /^(?:[\w-]*\[[^\]]*\]|[\w-]+):/;

/*
 * Blanks comments, keeping line numbers so matches can be reported. Copied
 * from check-v1.mjs (which runs on import, so it cannot be imported); keep
 * the two in step. Strings and template literals are tracked, so a `/*` or
 * `//` inside one does not swallow the code after it.
 */
function blankComments(src) {
  let out = "";
  let i = 0;
  // "`" = inside a template literal; "{" = inside a `${}` or a brace in one.
  const stack = [];
  while (i < src.length) {
    let end;
    if (stack.at(-1) === "`") {
      end = i + templateStep(src, i, stack);
    } else if (src[i] === "/" && (src[i + 1] === "/" || src[i + 1] === "*")) {
      end = commentEnd(src, i);
      out += src.slice(i, end).replace(/[^\n]/g, " ");
      i = end;
      continue;
    } else if (src[i] === '"' || src[i] === "'") {
      end = stringEnd(src, i);
    } else {
      codeStep(src[i], stack);
      end = i + 1;
    }
    out += src.slice(i, end);
    i = end;
  }
  return out;
}

/* CSS has only block comments, and a `//` in a url() is not one. */
function blankCssComments(src) {
  return src.replace(/\/\*[\s\S]*?(?:\*\/|$)/g, (c) =>
    c.replace(/[^\n]/g, " "),
  );
}

/* Index just past the line or block comment that starts at i. */
function commentEnd(src, i) {
  if (src[i + 1] === "/") {
    const newline = src.indexOf("\n", i);
    return newline === -1 ? src.length : newline;
  }
  const close = src.indexOf("*/", i + 2);
  return close === -1 ? src.length : close + 2;
}

/* Index just past the '...' or "..." string that starts at i. An unclosed
 * string ends at the newline. */
function stringEnd(src, i) {
  let j = i + 1;
  while (j < src.length && src[j] !== src[i] && src[j] !== "\n") {
    j += src[j] === "\\" ? 2 : 1;
  }
  return j + 1;
}

/* One step inside a template literal: how many characters to copy. Closing
 * the literal or opening `${` updates the stack. */
function templateStep(src, i, stack) {
  if (src[i] === "\\") {
    return 2;
  }
  if (src[i] === "`") {
    stack.pop();
    return 1;
  }
  if (src[i] === "$" && src[i + 1] === "{") {
    stack.push("{");
    return 2;
  }
  return 1;
}

/* Tracks template literals and the braces inside their `${}` expressions. */
function codeStep(c, stack) {
  if (c === "`") {
    stack.push("`");
  } else if (c === "{" && stack.length > 0) {
    stack.push("{");
  } else if (c === "}" && stack.length > 0) {
    stack.pop();
  }
}

/*
 * The text of every string and template literal in comment-blanked source,
 * as { text, index } with index the offset of the text's first character.
 * Code outside literals is replaced by spaces, and a `${}` expression ends one
 * piece of template text and starts the next (its own literals are yielded
 * too), so a match can never span code.
 */
function literals(src) {
  const pieces = [];
  const stack = [];
  let piece = null;
  let i = 0;
  while (i < src.length) {
    if (stack.at(-1) === "`") {
      piece ??= { text: "", index: i };
      const step = templateStep(src, i, stack);
      if (stack.at(-1) !== "`") {
        // The literal closed, or a `${` opened.
        pieces.push(piece);
        piece = null;
      } else {
        piece.text += src.slice(i, i + step);
      }
      i += step;
    } else if (src[i] === '"' || src[i] === "'") {
      const end = stringEnd(src, i);
      const close = src[end - 1] === src[i] ? end - 1 : end;
      pieces.push({ text: src.slice(i + 1, close), index: i + 1 });
      i = end;
    } else {
      codeStep(src[i], stack);
      i += 1;
    }
  }
  return pieces.filter((p) => p.text);
}

// A specifier: a quoted or backtick string with no interpolation.
const SPEC = "[\"'`]([^\"'`$]+)[\"'`]";
// The import forms check-v1.mjs reads, minus Vite globs.
const IMPORT_RES = [
  new RegExp(
    String.raw`\b(?:import|export)\s+(?:type\s+)?(?:[\w$*{}\s,]+?\s+from\s+)?${SPEC}`,
    "g",
  ),
  new RegExp(String.raw`\bimport\s*\(\s*${SPEC}\s*[,)]`, "g"),
  new RegExp(String.raw`\brequire\s*\(\s*${SPEC}\s*\)`, "g"),
];
const CSS_SPEC = /\.css(?:\?.*)?$/;

function lineAt(text, index) {
  return text.slice(0, index).split("\n").length;
}

/* Every whitespace-separated token in a literal, with its offset in the file. */
function* tokens({ text, index }) {
  for (const m of text.matchAll(/\S+/g)) {
    yield { token: m[0], index: index + m.index };
  }
}

/* A token that looks like a Tailwind utility without the `ui:` prefix. */
function isUnprefixedUtility(token) {
  let rest = token.startsWith("!") ? token.slice(1) : token;
  if (rest.startsWith("ui:")) {
    return false;
  }
  for (let m = rest.match(VARIANT_RE); m; m = rest.match(VARIANT_RE)) {
    rest = rest.slice(m[0].length);
    if (rest.startsWith("ui:")) {
      return false;
    }
  }
  return UTILITY_RE.test(rest);
}

/* A class token with the `!` important modifier at either end. */
function isImportantClass(token) {
  return /^![\w-[]|[\w\])]!$/.test(token) && /[-:]/.test(token);
}

// At-rules whose blocks hold theme keys or declarations, not v1 selectors.
const OPAQUE_AT_RULES = new Set([
  "theme",
  "utility",
  "custom-variant",
  "font-face",
  "keyframes",
]);

/* Splits a selector list on the commas outside (), [] and strings. */
function splitSelectors(prelude) {
  const parts = [];
  let depth = 0;
  let quote = null;
  let start = 0;
  for (let i = 0; i < prelude.length; i += 1) {
    const c = prelude[i];
    if (quote) {
      quote = c === quote ? null : quote;
    } else if (c === '"' || c === "'") {
      quote = c;
    } else if (c === "(" || c === "[") {
      depth += 1;
    } else if (c === ")" || c === "]") {
      depth -= 1;
    } else if (c === "," && depth === 0) {
      parts.push(prelude.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(prelude.slice(start));
  return parts.map((p) => p.trim());
}

/*
 * The selector lists that must be scoped: every block prelude that is not an
 * at-rule, not inside an opaque at-rule and not nested in another style rule
 * (a nested rule is already scoped by its parent). Grouping at-rules such as
 * @layer and @media are transparent. Returns { prelude, index }.
 */
function topLevelSelectors(css) {
  const found = [];
  // Per open block: "opaque", "group" (transparent at-rule) or "rule".
  const stack = [];
  let start = 0;
  let quote = null;
  for (let i = 0; i < css.length; i += 1) {
    const c = css[i];
    if (quote) {
      quote = c === quote ? null : quote;
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
    } else if (c === ";" || c === "}") {
      if (c === "}") {
        stack.pop();
      }
      start = i + 1;
    } else if (c === "{") {
      const raw = css.slice(start, i);
      const prelude = raw.trim();
      const index = start + raw.length - raw.trimStart().length;
      const at = prelude.match(/^@([\w-]+)/);
      if (stack.includes("opaque") || (at && OPAQUE_AT_RULES.has(at[1]))) {
        stack.push("opaque");
      } else if (at) {
        stack.push("group");
      } else {
        if (!stack.includes("rule")) {
          found.push({ prelude, index });
        }
        stack.push("rule");
      }
      start = i + 1;
    }
  }
  return found;
}

/* Every file under dir, relative and `/`-separated. Symlinks are reported by
 * check-v1.mjs, so they are skipped here. */
function walk(dir) {
  return fs
    .readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((d) => d.isFile())
    .map((d) =>
      path
        .relative(dir, path.join(d.parentPath, d.name))
        .replaceAll(path.sep, "/"),
    )
    .toSorted((a, b) => a.localeCompare(b));
}

const problems = [];
const report = (rel, line, msg) => {
  const where = line ? `${rel}:${line}` : rel;
  problems.push(`src/v1/${where}: ${msg}`);
};

function checkCode(rel) {
  const text = blankComments(fs.readFileSync(path.join(ROOT, rel), "utf8"));
  const top = rel.split("/")[0];

  // S5 applies to test files too: they would load the CSS the same way.
  for (const re of IMPORT_RES) {
    for (const m of text.matchAll(re)) {
      if (CSS_SPEC.test(m[1]) && !CSS_IMPORTERS.has(top)) {
        report(rel, lineAt(text, m.index), MSG.cssImport);
      }
    }
  }
  if (TEST_FILE.test(rel)) {
    return;
  }
  for (const m of text.matchAll(INLINE_STYLE_RE)) {
    report(rel, lineAt(text, m.index), MSG.inlineStyle);
  }
  if (rel === RAW_VALUES_TS) {
    return;
  }
  for (const literal of literals(text)) {
    for (const re of RAW_COLOUR_RES) {
      for (const m of literal.text.matchAll(re)) {
        report(rel, lineAt(text, literal.index + m.index), MSG.colour);
      }
    }
    for (const m of literal.text.matchAll(ARBITRARY_UNIT_RE)) {
      report(rel, lineAt(text, literal.index + m.index), MSG.pixel);
    }
    for (const { token, index } of tokens(literal)) {
      if (isImportantClass(token)) {
        report(rel, lineAt(text, index), MSG.important);
      }
      if (isUnprefixedUtility(token)) {
        report(rel, lineAt(text, index), `'${token}': ${MSG.unprefixed}`);
      }
    }
  }
}

function checkCss(rel) {
  const css = blankCssComments(fs.readFileSync(path.join(ROOT, rel), "utf8"));
  const at = (re, msg) => {
    for (const m of css.matchAll(re)) {
      report(rel, lineAt(css, m.index), msg);
    }
  };
  if (rel !== GENERATED_CSS) {
    for (const re of RAW_COLOUR_RES) {
      at(re, MSG.colour);
    }
    at(CSS_UNIT_RE, MSG.pixel);
  }
  at(CSS_IMPORTANT_RE, MSG.important);
  at(COLOUR_SCHEME_RE, MSG.colourScheme);
  for (const { prelude, index } of topLevelSelectors(css)) {
    for (const selector of splitSelectors(prelude)) {
      if (!/^\.v1(?![\w-])/.test(selector)) {
        report(rel, lineAt(css, index), `'${selector}': ${MSG.unscoped}`);
      }
    }
  }
}

if (!fs.existsSync(ROOT)) {
  console.error(`check-v1-styles: ${ROOT} does not exist`);
  process.exit(2);
}

for (const rel of walk(ROOT)) {
  if (CODE_EXT.test(rel)) {
    checkCode(rel);
  } else if (CSS_EXT.test(rel)) {
    checkCss(rel);
  }
}

if (problems.length > 0) {
  console.error(problems.join("\n"));
  console.error(`\ncheck-v1-styles: ${problems.length} problem(s).`);
  process.exit(1);
}
console.log("check-v1-styles: ok");

#!/usr/bin/env node
/*
 * Styling policy for the v1 frontend (src/v1/). Run by `lint:v1` after
 * check-v1.mjs; the rules and their reasons are in src/v1/README.md.
 *
 *   S1  No inline style: a JSX `style` attribute may hold only an object
 *       literal whose every key is a CSS custom property (`"--page-aspect"`),
 *       the channel for runtime geometry that `ui:aspect-(--page-aspect)`
 *       reads. A string, a variable, a spread or a plain key fails.
 *   S2  No raw colour: hex, rgb()/hsl()/oklch()/oklab()/color(), a
 *       Tailwind palette utility (`-red-500`, `-white`), or a named colour
 *       as an arbitrary value (`text-[red]`, `[color:tomato]`), as a whole
 *       value (`fill="red"`) or in a CSS declaration (`color: white`).
 *   S3  No raw pixel value: a px/rem/em/pt/vh/vw length anywhere in an
 *       arbitrary value (`[13px]`, `[200px_1fr]`, `[calc(100%-13px)]`) or
 *       in CSS.
 *   S4  No !important: a `!` class modifier, or `!important` in CSS.
 *   S5  CSS is imported only from app/ and styles/.
 *   S6  Every CSS selector starts with `.v1` and stays inside it: a sibling
 *       combinator right after the root (`.v1 + div`, or `& ~ div` nested
 *       directly in the root) selects outside v1. Not checked inside @theme, @utility,
 *       @custom-variant, @font-face and @keyframes.
 *   S7  CSS never reads prefers-color-scheme; data-theme sets the mode.
 *   S8  Every Tailwind utility carries the `ui:` prefix, and carries it
 *       first (`ui:hover:bg-primary`): Tailwind 4 generates nothing for a
 *       prefix after a variant (`hover:ui:bg-primary`). An unprefixed class
 *       in v1 renders with v0's theme whenever v0 already uses that class
 *       name, and silently does nothing otherwise.
 *
 * In TypeScript, S2 to S4 and S8 read only class strings: the value of a
 * `className` attribute or an argument of cn()/cva()/clsx()/cx() (however
 * short, so `className="flex"` counts; in cva() the base string, the variant
 * values and a compound `class`, never a variant name or choice such as
 * `defaultVariants: { variant: "outline" }`), and any other string or template
 * literal that looks like a class list (see isClassString), so a non-null
 * `!`, a hex-looking identifier or a value such as "outline" or "pt-BR" never
 * matches. One S2 check reads every literal: a string that is entirely a
 * colour (`fill="#ff0000"`, "rgb(1 2 3)", "red") fails wherever it appears,
 * while "Run #1234" does not. Test files are skipped for them; the raw values
 * live in styles/tokens.json, which is not code. S1 matches only a JSX
 * `style=` attribute.
 * In CSS, comments are blanked first; the generated styles/tokens.css is
 * skipped for S2 and S3 only. One escape hatch, for S3 only: a CSS line that
 * ends with the comment `/* v1-styles-allow: forced-colors outline *\/` may
 * hold a pixel value. It exists for the focus utility's transparent outline,
 * which forced-colors mode paints in place of the box-shadow ring.
 *
 * S8 checks a list of utility stems, not a Tailwind parse: a missing stem is a
 * false negative. A bare stem counts only when it is a whole utility (`flex`),
 * so a string such as "font" or "top" is not flagged.
 *
 * blankComments and its helpers are copied from check-v1.mjs, which runs on
 * import and so cannot be imported; keep the two in step. As there, JSX text
 * is parsed as code, so an apostrophe in it ("don't") opens a string to the
 * end of the line; the class-string test keeps such text from being reported.
 *
 * It always checks the src/v1 beside this script, like
 * check-v1.mjs; the fixtures in test-fixtures/v1-boundary/ rely on that.
 */
import fs from "node:fs";
import path from "node:path";

const ROOT = path.join(import.meta.dirname, "..", "src", "v1");

const CODE_EXT = /\.(ts|tsx|mts|cts)$/;
const TEST_FILE = /\.(test|spec)\.(ts|tsx|mts|cts)$/;
const GENERATED_CSS = "styles/tokens.css";
// Folders whose files may import a .css file.
const CSS_IMPORTERS = new Set(["app", "styles"]);

const MSG = {
  inlineStyle:
    "No inline style under v1; style with tokens and Tailwind. A style attribute may set only CSS custom properties (--name) that ui: classes read.",
  colour: "No raw colour under v1; use a token from styles/tokens.json.",
  pixel: "No raw pixel value under v1; use a token or the spacing scale.",
  important: "No !important under v1.",
  cssImport: "CSS is imported only from app/ and styles/ under v1.",
  unscoped: "Every v1 selector is scoped to .v1.",
  sibling:
    "Every v1 selector is scoped to .v1; a sibling combinator right after the root (.v1 + x, & ~ x) selects outside it.",
  prefixOrder:
    "The ui: prefix comes first (ui:hover:bg-primary, not hover:ui:bg-primary); Tailwind 4 generates nothing for a prefix after a variant.",
  colourScheme:
    "v1 never reads prefers-color-scheme in CSS; mode comes from data-theme.",
  unprefixed:
    "No unprefixed Tailwind utility under v1; write ui:<utility>. An unprefixed class renders with v0's theme whenever v0 already uses that class name, and silently does nothing otherwise.",
};

const PALETTE =
  "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const RAW_COLOUR_RES = [
  /#[0-9a-fA-F]{3,8}(?![\w-])/g,
  /(?<![\w-])(?:rgba?|hsla?|oklch|oklab|color)\(/g,
  new RegExp(String.raw`-(?:${PALETTE})-\d{2,3}(?![\w-])`, "g"),
  /-(?:white|black)(?![\w-])/g,
];
// A literal that is nothing but a colour: `fill="#ff0000"`, "rgb(1 2 3)".
const WHOLE_COLOUR_RES = [
  /^#[0-9a-fA-F]{3,8}$/,
  /^(?:rgba?|hsla?|oklch|oklab|color)\(/,
];
// CSS named colours an arbitrary value might carry. Not all 148: the common
// ones. transparent and currentcolor are listed but allowed (see below).
const NAMED_COLOURS = new Set([
  "black",
  "white",
  "red",
  "green",
  "blue",
  "yellow",
  "orange",
  "purple",
  "pink",
  "gray",
  "grey",
  "silver",
  "tomato",
  "navy",
  "teal",
  "maroon",
  "olive",
  "lime",
  "aqua",
  "cyan",
  "magenta",
  "fuchsia",
  "gold",
  "indigo",
  "violet",
  "brown",
  "coral",
  "crimson",
  "salmon",
  "transparent",
  "currentcolor",
]);
// The focus utility and shadcn patterns use these, so they stay allowed.
const ALLOWED_NAMED_COLOURS = new Set(["transparent", "currentcolor"]);
// An arbitrary value holding one word, after an optional `property:` label:
// `text-[red]`, `[color:tomato]`, `bg-[color:navy]`.
const ARBITRARY_WORD_RE = /(?:-|(?<![\w-]))\[(?:[\w-]+:)?([a-zA-Z]+)\]/g;
// A length in a Tailwind arbitrary value, anywhere inside the brackets:
// `w-[13px]`, `p-[1.5rem]`, `grid-cols-[200px_1fr]`, `w-[calc(100%-13px)]`.
// The unit may be followed by `_`, Tailwind's separator inside brackets.
const ARBITRARY_UNIT_RE = /\[[^\]\s]*\d(?:px|rem|em|vh|vw|pt)(?![A-Za-z-])/g;
// A CSS length in a unit: `3px`, `.5rem`, `-1em`, `100vh`.
const CSS_UNIT_RE =
  /(?<![\w.])(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem|em|pt|vh|vw)(?![\w-])/g;
// A CSS declaration's value (after the first `:` of `prop: value`).
const CSS_DECLARATION_RE = /(?<![\w-])[\w-]+\s*:\s*([^;{}]+)/g;
// The S3 escape hatch for a CSS line (see the header).
const PIXEL_ALLOW_RE =
  /\/\*\s*v1-styles-allow: forced-colors outline\s*\*\/\s*$/;
const CSS_IMPORTANT_RE = /!\s*important\b/g;
const COLOUR_SCHEME_RE = /prefers-color-scheme/g;
// A JSX attribute: `<div style={…}`, `style = {…}` or `style="…"`, not
// `const style = {…}` (whose `=` is followed by a brace too, but the regex
// needs a quote or an opening brace right after it, and `{…}` there holds
// an object, which S1's custom-property allowance still judges).
const INLINE_STYLE_RE = /(?<=[\s{])style\s*=\s*[{"]/g;
// Where a string is a class list by position: the value of className=, or an
// argument of cn()/cva()/clsx()/cx(). The match ends on the `=` or `(`.
const CLASS_SITE_RE = /\bclassName\s*=|\b(?:cn|cva|clsx|cx)\(/g;
// An object key that names a CSS custom property: "--x", '--x' or `--x`.
const CUSTOM_PROPERTY_KEY_RE = /^(?:"--[^"]+"|'--[^']+'|`--[^`$]+`)$/;

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
// `-` needs no escape outside a character class.
const stems = (lines) => lines.join(" ").split(" ").join("|");
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
 * as { text, index, id } with index the offset of the text's first character
 * and id shared by the pieces of one template literal.
 * Code outside literals is replaced by spaces, and a `${}` expression ends one
 * piece of template text and starts the next (its own literals are yielded
 * too), so a match can never span code.
 */
function literals(src) {
  const pieces = [];
  const stack = [];
  // The id of each open template literal, innermost last.
  const templates = [];
  let nextId = 0;
  let piece = null;
  let i = 0;
  while (i < src.length) {
    if (stack.at(-1) === "`") {
      piece ??= { text: "", index: i, id: templates.at(-1) };
      const depth = stack.length;
      const step = templateStep(src, i, stack);
      if (stack.length < depth) {
        templates.pop();
      }
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
      pieces.push({
        text: src.slice(i + 1, close),
        index: i + 1,
        id: nextId++,
      });
      i = end;
    } else {
      if (src[i] === "`") {
        templates.push(nextId++);
      }
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

/* A token that carries `ui:` after a variant (`hover:ui:bg-primary`), which
 * Tailwind 4 compiles to nothing; the prefix must come first. */
function prefixAfterVariant(token) {
  let rest = token.startsWith("!") ? token.slice(1) : token;
  let variants = 0;
  for (let m = rest.match(VARIANT_RE); m; m = rest.match(VARIANT_RE)) {
    rest = rest.slice(m[0].length);
    variants += 1;
    if (rest.startsWith("ui:")) {
      return variants > 0;
    }
  }
  return false;
}

const DEFINITE_CLASS_RES = [
  // `ui:` first, or after a variant (wrong, and S8 reports it): `ui:p-2`,
  // `!ui:p-2`, `md:ui:h-8!`.
  /(?:^!?|:)ui:/,
  /-\[[^\]]*\]/,
  new RegExp(String.raw`-(?:${PALETTE})-\d{2,3}(?![\w-])`),
];

/*
 * Ruling R7-3: S2, S3, S4 and S8 apply only to class strings. A literal is
 * one when it holds at least one definite utility (`ui:` prefix, an arbitrary
 * value `-[…]`, or a stock palette colour such as `-red-500`) or at least two
 * utility-shaped tokens (isUnprefixedUtility). So "outline", "pt-BR",
 * "Run #1234" and "Try re-running!" are values, while
 * "flex items-center gap-2" is a class list.
 */
function isClassString(text) {
  const words = text.split(/\s+/).filter(Boolean);
  if (words.some((w) => DEFINITE_CLASS_RES.some((re) => re.test(w)))) {
    return true;
  }
  return words.filter(isUnprefixedUtility).length >= 2;
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
 * at-rule and not inside an opaque at-rule. A prelude nested in another style
 * rule is already scoped by its parent unless it starts with `&` and a
 * sibling combinator (leavesRoot), so it is returned with nested: true.
 * Grouping at-rules such as @layer and @media are transparent.
 * Returns { prelude, index, nested }.
 */
function selectorPreludes(css) {
  const found = [];
  // Per open block: "opaque", "group" (transparent at-rule) or a style rule
  // as { root }, true when the rule's prelude is one compound on the root.
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
        const rules = stack.filter((entry) => typeof entry === "object");
        const nested = rules.length > 0;
        const parentIsRoot = rules.every((entry) => entry.root);
        found.push({ prelude, index, nested, parentIsRoot });
        stack.push({ root: parentIsRoot && isRootCompound(prelude, nested) });
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

/*
 * S1's one allowance. `open` indexes the `{` of a `style={…}` container (a
 * `style="…"` string never qualifies). True only when the container holds an
 * object literal and every entry is `"--name": value`: the attribute then
 * carries runtime numbers into custom properties that `ui:` classes read
 * (`ui:aspect-(--page-aspect)`), and the classes still own the visuals. A
 * variable, a call, a spread or a plain key is rejected: its keys are not
 * visible at the call site, or it styles the element directly.
 */
function isCustomPropertyStyle(text, open) {
  if (text[open] !== "{") {
    return false;
  }
  const close = matchingBrace(text, open);
  if (close < 0) {
    return false;
  }
  // The container must hold exactly one object literal: `{ {…} }`.
  const innerOpen = open + 1 + text.slice(open + 1, close).search(/\S/);
  const innerClose = matchingBrace(text, innerOpen);
  if (text[innerOpen] !== "{" || innerClose < 0) {
    return false;
  }
  if (text.slice(innerClose + 1, close).trim() !== "") {
    return false;
  }
  const body = text.slice(innerOpen + 1, innerClose);
  return topLevelSplit(body, ",").every((entry) => {
    const e = entry.trim();
    if (e === "") {
      return true; // a trailing comma
    }
    const [key] = topLevelSplit(e, ":");
    return key.length < e.length && CUSTOM_PROPERTY_KEY_RE.test(key.trim());
  });
}

/* Index of the `}` closing the `{` at `open`, skipping strings; -1 if none. */
function matchingBrace(text, open) {
  let depth = 0;
  let i = open;
  while (i < text.length) {
    const c = text[i];
    if (c === '"' || c === "'" || c === "`") {
      i = skipString(text, i);
      continue;
    }
    if (c === "{" || c === "(" || c === "[") {
      depth += 1;
    } else if (c === "}" || c === ")" || c === "]") {
      depth -= 1;
      if (depth === 0) {
        return c === "}" ? i : -1;
      }
    }
    i += 1;
  }
  return -1;
}

/* Splits `text` on `sep` at bracket depth 0, outside strings. */
function topLevelSplit(text, sep) {
  const parts = [];
  let depth = 0;
  let start = 0;
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === '"' || c === "'" || c === "`") {
      i = skipString(text, i);
      continue;
    }
    if (c === "{" || c === "(" || c === "[") {
      depth += 1;
    } else if (c === "}" || c === ")" || c === "]") {
      depth -= 1;
    } else if (c === sep && depth === 0) {
      parts.push(text.slice(start, i));
      start = i + 1;
    }
    i += 1;
  }
  parts.push(text.slice(start));
  return parts;
}

/* Index just past the string or template literal that starts at i. */
function skipString(text, i) {
  const quote = text[i];
  let j = i + 1;
  while (j < text.length && text[j] !== quote) {
    if (text[j] === "\\") {
      j += 1;
    } else if (quote === "`" && text[j] === "$" && text[j + 1] === "{") {
      j = matchingBrace(text, j + 1);
      if (j < 0) {
        return text.length;
      }
    }
    j += 1;
  }
  return j + 1;
}

/*
 * The start index (first character after the quote) of every string or
 * template literal that sits in a class position: `className="…"`, anywhere
 * inside `className={…}`, or anywhere inside cn(…)/cva(…)/clsx(…)/cx(…).
 * Those are class lists by position, so S2 to S4 and S8 read them even when
 * they hold a single word that isClassString would skip (`"flex"`).
 */
function classSiteLiterals(text) {
  const starts = new Set();
  for (const m of text.matchAll(CLASS_SITE_RE)) {
    const isCva = m[0].startsWith("cva(");
    // A call: scan its parentheses. An attribute: skip spaces, then a quote
    // starts one literal and a brace starts an expression to scan.
    let i = m.index + m[0].length - 1;
    if (!m[0].endsWith("(")) {
      i += 1;
      while (i < text.length && /\s/.test(text[i])) {
        i += 1;
      }
      if (text[i] === '"' || text[i] === "'" || text[i] === "`") {
        starts.add(i + 1);
        continue;
      }
      if (text[i] !== "{") {
        continue;
      }
    }
    // keys[d] is the property name the value at bracket depth d sits under,
    // read for cva() only, where variant names and choices are not classes.
    const keys = [];
    let depth = 0;
    let lastWord = "";
    while (i < text.length) {
      const c = text[i];
      if (c === '"' || c === "'" || c === "`") {
        const end = skipString(text, i);
        lastWord = text.slice(i + 1, end - 1);
        if (!isCva || cvaClassPosition(text, end, keys, depth)) {
          starts.add(i + 1);
        }
        i = end;
        continue;
      }
      if (/[A-Za-z_$]/.test(c)) {
        let j = i + 1;
        while (j < text.length && /[\w$]/.test(text[j])) {
          j += 1;
        }
        lastWord = text.slice(i, j);
        i = j;
        continue;
      }
      if (c === ":" && depth > 0) {
        keys[depth] = lastWord;
      } else if (c === "{" || c === "(" || c === "[") {
        depth += 1;
        keys[depth] = undefined;
      } else if (c === "}" || c === ")" || c === "]") {
        depth -= 1;
        if (depth === 0) {
          break;
        }
      }
      i += 1;
    }
  }
  return starts;
}

/*
 * In cva(), a literal that ends at `end` supplies classes unless it is a
 * property name (`"sm": …`), sits under defaultVariants (a choice), or sits
 * in compoundVariants under a key other than class/className (a choice to
 * match). The base string and the values under variants are classes.
 */
function cvaClassPosition(text, end, keys, depth) {
  let j = end;
  while (j < text.length && /\s/.test(text[j])) {
    j += 1;
  }
  if (text[j] === ":") {
    return false;
  }
  const chain = keys.slice(1, depth + 1);
  if (chain.includes("defaultVariants")) {
    return false;
  }
  if (chain.includes("compoundVariants")) {
    return keys[depth] === "class" || keys[depth] === "className";
  }
  return true;
}

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
    if (!isCustomPropertyStyle(text, m.index + m[0].length - 1)) {
      report(rel, lineAt(text, m.index), MSG.inlineStyle);
    }
  }
  const pieces = literals(text);
  // A template literal is judged as a whole, across its `${}` expressions.
  const textById = new Map();
  for (const { id, text: t } of pieces) {
    textById.set(id, `${textById.get(id) ?? ""} ${t}`);
  }
  const classSites = classSiteLiterals(text);
  for (const literal of pieces) {
    const trimmed = literal.text.trim();
    const word = trimmed.toLowerCase();
    if (
      WHOLE_COLOUR_RES.some((re) => re.test(trimmed)) ||
      (NAMED_COLOURS.has(word) && !ALLOWED_NAMED_COLOURS.has(word))
    ) {
      report(rel, lineAt(text, literal.index), MSG.colour);
      continue;
    }
    if (
      !classSites.has(literal.index) &&
      !isClassString(textById.get(literal.id))
    ) {
      continue;
    }
    for (const re of RAW_COLOUR_RES) {
      for (const m of literal.text.matchAll(re)) {
        report(rel, lineAt(text, literal.index + m.index), MSG.colour);
      }
    }
    for (const m of literal.text.matchAll(ARBITRARY_WORD_RE)) {
      const word = m[1].toLowerCase();
      if (NAMED_COLOURS.has(word) && !ALLOWED_NAMED_COLOURS.has(word)) {
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
      if (prefixAfterVariant(token)) {
        report(rel, lineAt(text, index), `'${token}': ${MSG.prefixOrder}`);
      }
      if (isUnprefixedUtility(token)) {
        report(rel, lineAt(text, index), `'${token}': ${MSG.unprefixed}`);
      }
    }
  }
}

function checkCss(rel) {
  const source = fs.readFileSync(path.join(ROOT, rel), "utf8");
  const css = blankCssComments(source);
  // 1-based numbers of the lines that carry the S3 escape-hatch marker.
  const pixelAllowed = new Set(
    source
      .split("\n")
      .flatMap((line, i) => (PIXEL_ALLOW_RE.test(line) ? [i + 1] : [])),
  );
  const at = (re, msg, skip = new Set()) => {
    for (const m of css.matchAll(re)) {
      const line = lineAt(css, m.index);
      if (!skip.has(line)) {
        report(rel, line, msg);
      }
    }
  };
  if (rel !== GENERATED_CSS) {
    for (const re of RAW_COLOUR_RES) {
      at(re, MSG.colour);
    }
    for (const m of css.matchAll(CSS_DECLARATION_RE)) {
      // Words of the value, outside var(--…) and other function arguments.
      for (const word of m[1]
        .toLowerCase()
        .matchAll(/(?<![\w-])[a-z]+(?![\w-(])/g)) {
        if (NAMED_COLOURS.has(word[0]) && !ALLOWED_NAMED_COLOURS.has(word[0])) {
          report(rel, lineAt(css, m.index), MSG.colour);
        }
      }
    }
    at(CSS_UNIT_RE, MSG.pixel, pixelAllowed);
  }
  at(CSS_IMPORTANT_RE, MSG.important);
  at(COLOUR_SCHEME_RE, MSG.colourScheme);
  for (const { prelude, index, nested, parentIsRoot } of selectorPreludes(
    css,
  )) {
    for (const selector of splitSelectors(prelude)) {
      if (!nested && !/^\.v1(?![\w-])/.test(selector)) {
        report(rel, lineAt(css, index), `'${selector}': ${MSG.unscoped}`);
      } else if (leavesRoot(selector, nested, parentIsRoot)) {
        report(rel, lineAt(css, index), `'${selector}': ${MSG.sibling}`);
      }
    }
  }
}

/*
 * True when the selector's subject can sit outside the v1 root: its first
 * compound is the root (`.v1…` at top level; `&…` in a nested rule whose
 * enclosing rules are all the root itself) and the combinator right after
 * it is `+` or `~`. Any later combinator keeps the subject inside
 * (`.v1 > a + b`), a nested selector without `&` is an implicit descendant,
 * and `& + x` under `.v1 .menu` resolves to `.v1 .menu + x`, inside v1.
 */
function leavesRoot(selector, nested, parentIsRoot) {
  if (nested && (!selector.startsWith("&") || !parentIsRoot)) {
    return false;
  }
  const next = selector.slice(rootCompoundEnd(selector)).trimStart()[0];
  return next === "+" || next === "~";
}

/*
 * True when some comma-separated part of the prelude is one compound on the
 * root: `.v1` or `.v1[data-theme="dark"]` at top level, `&:hover` or `&.x`
 * in a nested rule. A child rule of such a prelude that starts `& +` leaves
 * v1; a child of `.v1 .menu`, or of a nested `.menu`, does not.
 */
function isRootCompound(prelude, nested) {
  return splitSelectors(prelude).some(
    (selector) =>
      (nested ? selector.startsWith("&") : /^\.v1(?![\w-])/.test(selector)) &&
      rootCompoundEnd(selector) === selector.length,
  );
}

/* Index of the first combinator outside brackets and quotes, else length. */
function rootCompoundEnd(selector) {
  let depth = 0;
  let quote = null;
  for (let i = 0; i < selector.length; i += 1) {
    const c = selector[i];
    if (quote) {
      quote = c === quote ? null : quote;
    } else if (c === '"' || c === "'") {
      quote = c;
    } else if (c === "(" || c === "[") {
      depth += 1;
    } else if (c === ")" || c === "]") {
      depth -= 1;
    } else if (depth === 0 && /[\s>+~]/.test(c)) {
      return i;
    }
  }
  return selector.length;
}

if (!fs.existsSync(ROOT)) {
  console.error(`check-v1-styles: ${ROOT} does not exist`);
  process.exit(2);
}

for (const rel of walk(ROOT)) {
  if (CODE_EXT.test(rel)) {
    checkCode(rel);
  } else if (rel.endsWith(".css")) {
    checkCss(rel);
  }
}

if (problems.length > 0) {
  console.error(problems.join("\n"));
  console.error(`\ncheck-v1-styles: ${problems.length} problem(s).`);
  process.exit(1);
}
console.log("check-v1-styles: ok");

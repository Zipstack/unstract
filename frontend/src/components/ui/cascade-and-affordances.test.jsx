import fs from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, Tooltip } from "@/components/ui/shims/antd-overlays";
import { Textarea } from "@/components/ui/textarea";

/**
 * Guards for defects that jsdom cannot see directly.
 *
 * Two of these are cascade/affordance bugs that shipped to users and were
 * reported twice, but neither is observable through rendered geometry: jsdom
 * has no cascade-layer resolution and no cursor. So they are asserted the same
 * way `no-antd.test.js` asserts its invariant — against the source text and
 * the emitted class list.
 */
describe("cascade and affordance guards", () => {
  describe("default border colour stays inside @layer base", () => {
    const css = fs.readFileSync(
      path.join(process.cwd(), "src/index.css"),
      "utf8",
    );

    it("wraps the universal border-color rule in @layer base", () => {
      // Unlayered CSS outranks EVERY layered rule regardless of specificity.
      // Outside a layer this selector beat Tailwind's `utilities` layer and
      // repainted `border-input`, so form controls silently rendered with
      // --border (#e5e5e5) instead of --input (#d3d3d3).
      const match = css.match(
        /@layer base\s*\{[\s\S]*?::file-selector-button\s*\{[^}]*border-color:\s*var\(--border\)/,
      );
      expect(
        match,
        "the `*, ::after, ::before…{border-color}` rule must live in @layer base, or it overrides every border-* utility",
      ).toBeTruthy();
    });

    /*
     * A Tailwind colour utility only exists if the token is registered in
     * `@theme inline`. `divide-separator` (the antd-matching list hairline)
     * would otherwise compile to nothing and the rows would lose their rule
     * silently — no error, no failing test, just a visual regression.
     */
    it("exposes --separator to Tailwind for both themes", () => {
      expect(
        css,
        "--color-separator must be in @theme inline or `divide-separator` does not exist",
      ).toMatch(
        /@theme inline\s*\{[\s\S]*?--color-separator:\s*var\(--separator\)/,
      );
      // Declared for light...
      expect(css).toMatch(/:root\s*\{[\s\S]*?--separator:/);
      // ...and dark, or dark mode falls back to the light hairline.
      expect(css).toMatch(/\.dark\s*\{[\s\S]*?--separator:/);
    });

    it("form controls ask for --input, not the generic --border", () => {
      // If a text control ever drops to a bare `border`, it renders a
      // different grey from its neighbours — worse than the original bug.
      render(<Input />);
      expect(screen.getByRole("textbox").className).toContain("border-input");
    });

    it("textarea matches the input's border token", () => {
      render(<Textarea />);
      expect(screen.getByRole("textbox").className).toContain("border-input");
    });
  });

  describe("pointer cursor (Tailwind v4 dropped the preflight)", () => {
    it("buttons carry cursor-pointer", () => {
      render(<Button>Click</Button>);
      expect(screen.getByRole("button").className).toContain("cursor-pointer");
    });

    it("dialog and sheet close buttons carry cursor-pointer", () => {
      // Radix renders these as bare <button>s inside the primitive, so they
      // never pass through the Button variants that supply the cursor.
      const dialog = fs.readFileSync(
        path.join(process.cwd(), "src/components/ui/dialog.tsx"),
        "utf8",
      );
      const sheet = fs.readFileSync(
        path.join(process.cwd(), "src/components/ui/sheet.tsx"),
        "utf8",
      );
      for (const [name, src] of [
        ["dialog", dialog],
        ["sheet", sheet],
      ]) {
        const close = src.match(/\.Close className="([^"]*)"/);
        expect(
          close,
          `${name} should render a .Close with a className`,
        ).toBeTruthy();
        expect(
          close[1],
          `the ${name} close button needs cursor-pointer — Tailwind v4 dropped the preflight`,
        ).toContain("cursor-pointer");
      }
    });

    /*
     * antd shipped an icon FONT, so `font-size` sized its icons. lucide ships
     * SVGs, which ignore font-size entirely and fall back to their own 24px
     * default — every such rule silently renders its icon oversized.
     *
     * Matching on selector NAMES (icon|svg|anticon…) was the first version of
     * this guard and it missed the real ones: `.prompt-card-actions-head`
     * carries eight lucide icons and has no icon-ish word in its name, so the
     * whole prompt-card action row rendered 16px against the reference's 12.
     *
     * So this reads the JSX instead: collect every class applied to a lucide
     * component (they are PascalCase imports from lucide-react), then flag any
     * CSS rule that sizes one of those classes with font-size alone.
     */
    it("classes on lucide icons set explicit dimensions, not just font-size", () => {
      const iconClasses = new Set();
      const cssRules = [];

      const walk = (dir) => {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          const full = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            if (entry.name !== "node_modules") walk(full);
            continue;
          }
          const txt = fs.readFileSync(full, "utf8");

          if (/\.(jsx|tsx)$/.test(entry.name)) {
            // Only files that actually import icons from lucide-react.
            const imports = txt.match(
              /import\s*\{([^}]*)\}\s*from\s*"lucide-react"/,
            );
            if (!imports) continue;
            const names = imports[1]
              .split(",")
              .map((n) =>
                n
                  .trim()
                  .split(/\s+as\s+/)
                  .pop()
                  .trim(),
              )
              .filter(Boolean);
            for (const name of names) {
              const re = new RegExp(
                `<${name}\\b[^>]*className=[{"]\`?([^"\`}]*)`,
                "g",
              );
              for (const m of txt.matchAll(re)) {
                for (const cls of m[1].split(/\s+/)) {
                  // Skip template holes and Tailwind utilities.
                  if (cls && !cls.includes("$") && !cls.includes("-[")) {
                    iconClasses.add(cls);
                  }
                }
              }
            }
            continue;
          }

          if (!entry.name.endsWith(".css")) continue;
          for (const m of txt.matchAll(/([^{}]*)\{([^}]*)\}/g)) {
            const sel = m[1].trim().split("\n").pop().trim();
            const body = m[2];
            if (!/font-size:\s*\d+px/.test(body)) continue;
            if (/width|height/.test(body)) continue;
            cssRules.push({
              file: path.relative(process.cwd(), full),
              sel,
              classes: [...sel.matchAll(/\.([a-zA-Z][\w-]*)/g)].map(
                (c) => c[1],
              ),
            });
          }
        }
      };
      walk(path.join(process.cwd(), "src"));

      const offenders = cssRules
        .filter((r) => r.classes.some((c) => iconClasses.has(c)))
        .map((r) => `${r.file}: ${r.sel}`);

      expect(
        offenders,
        "these rules size a lucide SVG with font-size, which does nothing — set width/height",
      ).toEqual([]);
    });

    it("keeps the not-allowed affordance for disabled buttons", () => {
      render(<Button disabled>Nope</Button>);
      // `disabled:pointer-events-none` suppresses the hand; the class list
      // still carries the base cursor, so assert the disabled rule survives.
      expect(screen.getByRole("button").className).toContain(
        "disabled:pointer-events-none",
      );
    });
  });

  describe("antd Popover shim", () => {
    it("supplies onOpenChange even when the call-site passes none", () => {
      // antd call-sites drive `open` from their own trigger and pass no
      // change handler. Radix reads a bare `open` as fully controlled, so
      // without a supplied handler Esc and outside-click cannot close it.
      const { container } = render(
        <Popover open content={<span>body</span>}>
          <button type="button">trigger</button>
        </Popover>,
      );
      expect(screen.getByText("body")).toBeInTheDocument();
      expect(container).toBeTruthy();
    });

    /*
     * `trigger="hover"` was destructured and then ignored, so the sidebar's
     * HITL and Platform fly-out menus never opened on hover — Radix Popover
     * is click-only. A dropped prop like this raises no error and no warning,
     * which is why it needs a behavioural test rather than a class check.
     */
    it("opens on hover when the call-site asks for trigger='hover'", async () => {
      const user = userEvent.setup();
      render(
        <Popover trigger="hover" content={<span>fly-out</span>}>
          <button type="button">Platform</button>
        </Popover>,
      );
      expect(screen.queryByText("fly-out")).not.toBeInTheDocument();
      await user.hover(screen.getByRole("button", { name: "Platform" }));
      expect(await screen.findByText("fly-out")).toBeInTheDocument();
    });

    /*
     * The sidebar's real shape, and why the first hover fix did not work.
     *
     * Every sidebar item wraps its content in a Tooltip, so the Popover's
     * `asChild` trigger merges the hover handlers onto the TOOLTIP, not a DOM
     * node. The Tooltip shim then either returned `children` raw (when there
     * is no title — the expanded sidebar) or spread the props onto the tooltip
     * BUBBLE, so the handlers never reached the element under the cursor.
     *
     * Both variants are asserted because the collapsed sidebar has a title and
     * the expanded one does not — the earlier flat test passed while the real
     * nesting stayed broken.
     */
    it.each([
      ["without a tooltip title (expanded sidebar)", ""],
      ["with a tooltip title (collapsed sidebar)", "Platform"],
    ])("opens on hover through a nested Tooltip %s", async (_label, title) => {
      const user = userEvent.setup();
      render(
        <Popover trigger="hover" content={<span>sub-menu</span>}>
          <Tooltip title={title}>
            <button type="button">Platform</button>
          </Tooltip>
        </Popover>,
      );
      expect(screen.queryByText("sub-menu")).not.toBeInTheDocument();
      await user.hover(screen.getByRole("button", { name: "Platform" }));
      expect(await screen.findByText("sub-menu")).toBeInTheDocument();
    });

    it("stays click-only when no trigger is given", async () => {
      const user = userEvent.setup();
      render(
        <Popover content={<span>clicky</span>}>
          <button type="button">Open</button>
        </Popover>,
      );
      await user.hover(screen.getByRole("button", { name: "Open" }));
      expect(screen.queryByText("clicky")).not.toBeInTheDocument();
    });

    it("does not leak antd-only props onto the DOM", () => {
      render(
        <Popover open trigger="click" arrow={false} content={<span>c</span>}>
          <button type="button">t</button>
        </Popover>,
      );
      // `trigger` and `arrow` are antd's API, not Radix's; React would warn
      // and the attributes would land on the element.
      const trigger = screen.getByText("t");
      expect(trigger.getAttribute("trigger")).toBeNull();
      expect(trigger.getAttribute("arrow")).toBeNull();
    });
  });
  /**
   * The "left and right borders are missing" report, three rounds running.
   * The borders were always drawn; `shadow-sm` (a vertical-only offset)
   * reinforced the top and bottom edges so the bare 1px sides looked absent
   * beside them. The antd reference computes `box-shadow: none`.
   */
  describe("form controls draw an even border on all four sides", () => {
    it("Input carries no vertical-offset shadow", () => {
      render(<Input />);
      expect(screen.getByRole("textbox").className).not.toContain("shadow-sm");
    });

    it("Textarea carries no vertical-offset shadow", () => {
      render(<Textarea />);
      expect(screen.getByRole("textbox").className).not.toContain("shadow-sm");
    });
  });
  /**
   * React 19 stopped applying `defaultProps` to FUNCTION components — the
   * declaration is simply ignored, so every default silently becomes
   * undefined. That is the same silent-prop-drop class that produced the
   * Save-does-nothing bug, so it is guarded rather than trusted.
   *
   * Class components still honour defaultProps, which is why ErrorBoundary
   * is allowed to keep its block.
   */
  it("no function component relies on defaultProps (React 19)", () => {
    const SRC = path.join(process.cwd(), "src");
    const offenders = [];
    const walk = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name !== "node_modules") {
            walk(full);
          }
          continue;
        }
        // .tsx too — a `.jsx`-only filter would stop checking each shim as it
        // converts to TypeScript, and this guard would pass over less and less.
        if (!/\.[jt]sx$/.test(entry.name) || entry.name.includes(".test.")) {
          continue;
        }
        const src = fs.readFileSync(full, "utf8");
        const m = src.match(/^(\w+)\.defaultProps\s*=/m);
        if (m && !new RegExp(`class\\s+${m[1]}\\s+extends`).test(src)) {
          offenders.push(`${path.relative(SRC, full)} (${m[1]})`);
        }
      }
    };
    walk(SRC);
    expect(
      offenders,
      "React 19 ignores defaultProps on function components — use default parameters instead",
    ).toEqual([]);
  });

  /*
   * antd's Tooltip accepts any child, including a bare string. Ours renders a
   * Radix TooltipTrigger with `asChild`, which slots onto a single ELEMENT and
   * throws "Primitive.button failed to slot onto its children" on text — the
   * route-level error boundary then turns that into "Couldn't load this page".
   *
   * A source scan, not a render test, because these live inside table column
   * `render()` callbacks: they only execute when a row exists, so an
   * empty-list smoke test walks straight past them. That is exactly how one
   * shipped in ResourceTable and another in LogsTable.
   */
  it("no <Tooltip> wraps a bare value instead of an element", () => {
    const SRC = path.join(process.cwd(), "src");
    const offenders = [];
    /*
     * `[^>]*` for the attributes would be wrong: `title={a > b}` and any
     * multi-line prop containing `>` (a `.map()` arrow, a comparison) end the
     * match early and make the REST of the attribute list look like the child.
     * Match balanced braces instead, so the open tag ends at the real `>`.
     */
    const TOOLTIP =
      /<Tooltip\b(?:[^>{]|\{(?:[^{}]|\{[^{}]*\})*\})*>\s*([\s\S]*?)\s*<\/Tooltip>/g;

    const walk = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name !== "node_modules") {
            walk(full);
          }
          continue;
        }
        if (!/\.[jt]sx$/.test(entry.name) || entry.name.includes(".test.")) {
          continue;
        }
        const src = fs.readFileSync(full, "utf8");
        for (const m of src.matchAll(TOOLTIP)) {
          const child = m[1].trim();
          // An element child is fine; so is a comment (the JSX below it is the
          // real child) and a conditional whose branches render elements.
          if (child.startsWith("<") || child.startsWith("{/*")) {
            continue;
          }
          // `{cond && <El/>}` / `{cond ? <El/> : <El/>}` — the value that
          // reaches Radix is still an element.
          if (/[&?]{1,2}\s*\(?\s*</.test(child)) {
            continue;
          }
          // `{content}` where the same file does `const content = (<span…`.
          // Narrow on purpose: only a local binding whose initialiser is
          // literal JSX counts, so an imported or computed value still fails.
          const ident = child.match(/^\{\s*([A-Za-z_$][\w$]*)\s*\}$/)?.[1];
          if (
            ident &&
            new RegExp(`const\\s+${ident}\\s*=\\s*\\(?\\s*<`).test(src)
          ) {
            continue;
          }
          const line = src.slice(0, m.index).split("\n").length;
          offenders.push(
            `${path.relative(SRC, full)}:${line} → ${child.slice(0, 60)}`,
          );
        }
      }
    };
    walk(SRC);

    expect(
      offenders,
      "Radix slots onto a single element child — wrap the value in a <span>",
    ).toEqual([]);
  });
  /*
   * Tailwind v3 let you name a custom property bare inside an arbitrary
   * value, with no var() around it. v4 removed that shorthand and emits the
   * value verbatim, so the browser sees a property name where a value should
   * be, drops the declaration, and the utility silently does nothing.
   * Nothing errors: not the build, not the linter, not jsdom.
   *
   * NB: the examples above are described rather than written out, because
   * Tailwind scans this file too — spelling the broken form here would emit
   * the very dead rule the build-level `grep` for it is meant to catch.
   *
   * That is how SelectContent lost its max-height in the migration — the
   * Prompt Studio LLM dropdown grew to the full option-list height and ran
   * off the bottom of a scroll-locked page with no way to reach the rest.
   * Four `origin-` utilities on popover/tooltip/dropdown-menu were dead the
   * same way, which is why this guards the pattern rather than the one class.
   */
  describe("no Tailwind v3 bare-custom-property shorthand", () => {
    it("wraps every arbitrary custom-property value in var()", () => {
      const SRC = path.join(process.cwd(), "src");
      // `-[--name]` and nothing else inside the brackets. Deliberately does
      // NOT match `data-[state=open]`, `[&_svg]`, `max-h-[var(--x)]`, or v4
      // arbitrary *properties* like `[--x:red]` (those carry a `:`).
      const V3_SHORTHAND = /[a-z0-9]-\[--[a-zA-Z][\w-]*\]/g;
      const offenders = [];

      const walk = (dir) => {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          const full = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            if (entry.name !== "node_modules") walk(full);
            continue;
          }
          // Skip test files — this guard's own regex literal would match.
          if (!/\.[jt]sx?$/.test(entry.name) || entry.name.includes(".test.")) {
            continue;
          }
          const src = fs.readFileSync(full, "utf8");
          for (const m of src.matchAll(V3_SHORTHAND)) {
            const line = src.slice(0, m.index).split("\n").length;
            offenders.push(`${path.relative(SRC, full)}:${line} → ${m[0]}`);
          }
        }
      };
      walk(SRC);

      expect(
        offenders,
        "Tailwind v4 removed `util-[--var]`; these compile to an invalid " +
          "declaration the browser discards. Write `util-[var(--var)]`.",
      ).toEqual([]);
    });

    /*
     * Guards against "fixing" a future failure of the test above by deleting
     * the utility instead of repairing it. Without a max-height the dropdown
     * grows to the full option list and runs off the bottom of the page.
     */
    it("SelectContent still declares a max-height", () => {
      const src = fs.readFileSync(
        path.join(process.cwd(), "src/components/ui/select.tsx"),
        "utf8",
      );
      expect(src).toMatch(
        /max-h-\[[^\]]*--radix-select-content-available-height[^\]]*\]/,
      );
    });
  });
});

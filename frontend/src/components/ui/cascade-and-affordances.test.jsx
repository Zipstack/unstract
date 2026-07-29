import fs from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover } from "@/components/ui/shims/antd-overlays";
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
     * default — every such rule silently rendered a third too large.
     */
    it("icon CSS rules set explicit dimensions, not just font-size", () => {
      const offenders = [];
      const walk = (dir) => {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          const full = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            if (entry.name !== "node_modules") walk(full);
            continue;
          }
          if (!entry.name.endsWith(".css")) continue;
          const txt = fs.readFileSync(full, "utf8");
          for (const m of txt.matchAll(/([^{}]*)\{([^}]*)\}/g)) {
            const sel = m[1].trim().split("\n").pop().trim();
            const body = m[2];
            if (!/font-size:\s*\d+px/.test(body)) continue;
            if (!/icon|svg|anticon|glyph|chevron|caret/i.test(sel)) continue;
            if (/width|height/.test(body)) continue;
            offenders.push(`${path.relative(process.cwd(), full)}: ${sel}`);
          }
        }
      };
      walk(path.join(process.cwd(), "src"));
      expect(
        offenders,
        "these icon rules size by font-size only, which does nothing to an SVG",
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
});

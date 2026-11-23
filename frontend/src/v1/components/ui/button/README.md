# Buttons and links

The one button scale in v1 (P1-T02, UN-4272). Import everything from
`@v1/components/ui/button`.

| Component | Use it for |
| --- | --- |
| `Button` | An action with a text label |
| `IconButton` | An icon-only action: toolbars, row kebabs, on/off toggles |
| `Link` | Navigation inside text |
| `Kbd` | One key of a shortcut hint |
| `ButtonGroup` | Buttons joined into one control |

## Button

- `size`: `lg` 36, `md` 32 (default, the height of an input), `sm` 28,
  `xs` 24. There are no other heights.
- `variant`: `primary` (default), `secondary`, `outline`, `ghost`,
  `destructive`, `link`. Icons take the variant's text colour.
- `leadingIcon` and `trailingIcon` take a lucide icon (`ACTION_ICONS.add`),
  16px (14px at `xs`).
- `loading` shows a spinner in place of the leading icon and keeps the label.
  The button gets `aria-busy` and `aria-disabled`, not `disabled`, so it keeps
  focus. While loading it drops pointer-down, click and the keys Enter, Space
  and ArrowDown: its own handlers and a DropdownMenu, Popover or Dialog
  trigger's do not run (a loading `MenuButton` keeps its menu closed), a click
  does not reach a parent, and it cannot submit its form. Other keys, such as
  Tab, still reach its handlers. A trigger that opens on another event (a Tabs
  trigger on mouse-down) is not covered.
- `disabled` is the native attribute: opacity .5 and the not-allowed cursor.
  A click on it does nothing and does not reach its container.
- `type` defaults to `"button"`; pass `type="submit"` in a form.
- A router link that must look like a button takes
  `className={buttonVariants({ variant, size })}`.
- A dialog has at most one destructive button and it is never the default
  action: initial focus goes to Cancel (P1-T07). Prompt Studio's A12, C12
  and D08 draw a soft destructive button; v1 uses solid everywhere.

## IconButton

- `icon` (required): the lucide icon it shows, 16px (`ACTION_ICONS.edit`).
- `size`: `md` 32 (default, radius 8) or `sm` 28 (radius 6) in dense rows.
- `variant`: `ghost` (default) or `outline`.
- `selected` makes it a toggle: it sets `aria-pressed`, and the primary fill
  follows `aria-pressed`. Leave it out for a plain action; a Radix `Toggle`
  with `asChild` then sets `aria-pressed` and gets the same fill.
- It needs a name, and the types require one: `aria-label` or
  `aria-labelledby`. `IconButton.test.tsx` fails `typecheck:v1` if a nameless
  one ever compiles, and the gallery's axe scan reports one at run time.

## Link

- Inline, in the primary colour and underlined; it keeps the size of the text
  around it.
- `external` opens a new tab with `rel="noopener noreferrer"`, adds the
  external marker and the screen-reader text "(opens in a new tab)".
- `asChild` puts the link's classes on a router link instead of an `<a>`; it
  cannot be combined with `external`. `LINK_CLASS` holds the classes.

## Kbd and ButtonGroup

- `<Kbd>⌘</Kbd><Kbd>K</Kbd>`: one key per chip. The command palette's footer
  uses it.
- `ButtonGroup` is a `role="group"`; name it with `aria-label` when the
  buttons need context. Only the outer corners stay round, neighbouring
  borders overlap, and a focused button sits on top so its ring shows.

## States

Focus is `ui:focus-visible:focus-ring` on every part. Hover and active
(pressed) shades come from each variant's tokens.

## Tests

`Button.test.tsx`, `IconButton.test.tsx` and `Link.test.tsx` cover behaviour
and keyboard use. `markup.test.tsx` snapshots every gallery entry into
`__snapshots__/markup.md` and runs the accessibility scan on each. The
entries are in `button.gallery.tsx`, ready for P1-T01.

# Overlays

Side drawers, popovers, hover cards and tooltips (P1-T08, UN-4315), and the
parts every overlay shares, dialogs (P1-T07) included. Import everything from
`@v1/components/ui/overlay`. All render into the v1 portal container, so they
follow the theme.

| Component | Use it for | Focus | Closes with |
| --- | --- | --- | --- |
| `Drawer` | A record's detail at the right edge | Trapped; returns to the opener | Escape, the close button, a click on the dim layer |
| `Popover` | A small panel that may hold controls | Moves in, not trapped; Tab loops inside | Escape, a click or focus outside |
| `HoverCard` | A preview of what its trigger names | Never taken | Escape, pointer leave, blur |
| `Tooltip` | A short text label for a control | Never taken | Escape, pointer leave, blur |

Focus returns to the opener when an overlay closes. The one exception is a
popover closed by a click or focus outside: focus stays where the user put it.

## Drawer

```tsx
<Drawer
  trigger={<Button>Details</Button>}
  title="health-monitoring API"
  description="API deployment · owner ritwik"
  actions={<Button>View logs</Button>}
>
  <DrawerSection title="Last 5 runs" meta="all five succeeded">…</DrawerSection>
</Drawer>
```

- `title` (required), `description`, `leading` (a logo before the title),
  `badge` (a status chip after it).
- `size`: `md` 480 (default) or `lg` 640, never wider than the screen.
- `actions`: buttons for the bar at the bottom, primary first. The header and
  the bar stay put; the body scrolls.
- `trigger` is the opener itself (`asChild`). Leave it out and use `open` and
  `onOpenChange` when a row or a menu item opens the drawer; focus then goes
  back to that row, or to the menu's trigger once the menu has closed.
- `busy`: Escape, a click outside and the close button do nothing.
- Loading and error are the body's content: a `Skeleton`, or an
  `InlineAlert` with `onRetry`. A page passes its `QueryView` as the children.
- `DrawerSection`: `title` (shown upper-case) and `meta` (a note at its
  right). A rule separates sections.
- The page behind is not scroll-locked: the drawer leaves out Radix's
  `Dialog.Overlay`, which is what locks it. While it is open, Radix stops
  pointer events on the page, so the wheel scrolls the document, not a
  scroll area inside the page.

## Popover

- `Popover`, `PopoverTrigger` (pass `asChild` with a v1 button) and
  `PopoverContent`, as in Radix.
- `PopoverContent` needs a name: `title` (shown as its heading) or
  `aria-label`; the types require one. `description` adds a line under the
  title. `busy` keeps it open.
- It may hold buttons, links and fields.

## HoverCard

- `HoverCard` (`openDelay` 500, `closeDelay` 300), `HoverCardTrigger` (pass
  `asChild` with a focusable element such as `Link`) and `HoverCardContent`.
- It opens on hover and on keyboard focus. Radix makes its content
  untabbable, so it must hold nothing a user has to reach; use a Popover for
  that.

## Tooltip

```tsx
<Tooltip content="Copy endpoint">
  <IconButton aria-label="Copy" icon={ACTION_ICONS.copy} />
</Tooltip>
```

- `content` is a string, so a tooltip never holds interactive content. The
  trigger is described by it (`aria-describedby`).
- It opens after `TOOLTIP_DELAY_MS` (500) on hover and at once on keyboard
  focus. `side` (default `top`) and `align` place it.
- Each tooltip carries its own Radix provider; pages need no setup.
- A disabled button gets no pointer events, so its tooltip never shows.

## Shared parts

For any overlay built on a Radix Dialog or Popover, the dialogs included:

- `OVERLAY_SCRIM`: the dim layer's classes.
- `OverlayHeader`: title, description, `leading`, `badge` and a close button
  named "Close" (disabled while `busy`). Inside a Radix Dialog only. Without a
  description, pass `aria-describedby={undefined}` to the Content.
- `OverlayFooter`: the action bar; `align` `end` (default) or `start`.
- `dismissGuards(busy, own)`: spread onto the Content. Escape first clears a
  filled `SearchField`; a click on a toast never closes the overlay; while
  `busy`, neither Escape nor a click outside closes it. `own` handlers run
  first and may prevent the close themselves.
- `useReturnFocus(open)`: pass the result as `onCloseAutoFocus`. Focus goes
  back to what had it when the overlay opened, or, when that was a menu item
  that has since closed, to the menu's trigger.

## Tests

Each component has its own test file for behaviour and keyboard use;
`parts.test.tsx` covers the shared parts. `markup.test.tsx` snapshots every
gallery entry, open, into `__snapshots__/markup.md` and runs the
accessibility scan on each. The entries are in `overlay.gallery.tsx`, ready
for P1-T01.

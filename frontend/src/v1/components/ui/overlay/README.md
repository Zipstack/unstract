# Overlays

Side drawers, popovers, hover cards and tooltips (P1-T08, UN-4315), and the
parts the drawer and the dialogs (P1-T07) share. Import everything from
`@v1/components/ui/overlay`. All render into the v1 portal container, so they
follow the theme.

| Component | Use it for | Focus | Closes with |
| --- | --- | --- | --- |
| `Drawer` | A record's detail at the right edge | Trapped; returns to the opener | Escape, the close button, a click on the dim layer |
| `Popover` | A small panel that may hold controls | Moves in, not trapped; Tab loops inside | Escape, a click or focus outside |
| `HoverCard` | A preview of what its trigger names | Never taken | Escape, pointer leave, blur |
| `Tooltip` | A short text label for a control | Never taken | Escape, pointer leave, blur |

Focus returns to the opener when an overlay closes (see Drawer for how the
opener is found). A popover closed by a click or focus outside leaves focus
where the user put it. Focus lands on the page when no opener is left:

- the opener took no focus: a plain table row, or a clicked button in Safari;
- the page removed it, such as a drawer action that deletes its row (move
  focus yourself there);
- a context-menu item opened it from a row that never had focus.

Toasts sit above every overlay (drawers and dialogs, and the popovers, menus
and tooltips whose wrapper v0 pins at z-index 1500), so a toast they raise
shows and can be clicked, and Escape closes the newest toast first. A toast already showing
when a drawer opens stays visible but takes no clicks until it closes. A
modal hides toasts from keyboard and screen-reader users, so inside a drawer
put Retry or Undo in the drawer (an `InlineAlert`), not only on a toast.

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

- `title` (required text), `description`, `leading` (a logo before the
  title), `badge` (a status chip after it), `className` (on the panel).
- `size`: `md` 480 (default) or `lg` 640, never wider than the screen.
- `actions`: buttons for the bar at the bottom, primary first. The header and
  the bar stay put; the body scrolls.
- `trigger` is the opener itself (`asChild`); `defaultOpen` opens it at
  first render. Leave `trigger` out when another control opens the drawer:
  pass `open` and `onOpenChange`, or render it only while open (with `open`
  or `defaultOpen`).
  Focus then goes back to that control. When the control sat in a menu,
  submenu or popover that has closed, focus goes to the control that opened
  that, and failing that to the page control that last had focus (a command
  palette row returns to what had focus before the palette opened).
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
  title. `busy` keeps it open on Escape and a click outside; a click on its
  trigger still closes it.
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
  focus. `side` (default `top`) and `align` place it; `defaultOpen` shows it
  at first render.
- Other props, including those a parent `asChild` passes, go to the trigger,
  so `<PopoverTrigger asChild><Tooltip>…</Tooltip></PopoverTrigger>` works.
- Each tooltip carries its own Radix provider; pages need no setup.
- A disabled button gets no pointer events, so its tooltip never shows.

## Shared parts

For overlays built on a Radix Dialog, the dialogs included; a popover uses
`dismissGuards` only.

- `OVERLAY_SCRIM`: the dim layer's classes.
- `OverlayHeader`: `title` (text), description, `leading`, `badge`,
  `className`, `titleSize` (`page` 20, the default, or `section` 16 for a
  confirm) and a close button
  named "Close" (disabled while `busy`). Inside a Radix Dialog only: it
  throws inside an `AlertDialog`, so a confirm is a `Dialog` with
  `role="alertdialog"`. Without a description, pass
  `aria-describedby={undefined}` to the Content.
- `OverlayFooter`: the action bar; `align` `end` (default) or `start`.
- `dismissGuards(busy, own)`: spread onto the Content. Escape first clears a
  filled `SearchField`; while `busy`, neither Escape nor a click outside
  closes it. `own` handlers run first and may prevent the close themselves.
- `useReturnFocus(open)`: pass the controlled `open` and the result as
  `onCloseAutoFocus`. Focus goes back to what had it when the overlay opened,
  else to the nearest control still on the page that opened the menu,
  submenu or popover it sat in, else to the page control that last had focus.
  An overlay that closes and reopens in one task keeps its first opener, and
  unmounting while open counts as a close. An uncontrolled overlay opened
  from its own trigger needs no open state: Radix returns focus there.

## Tests

Each component has its own test file for behaviour and keyboard use;
`parts.test.tsx` covers the shared parts. `markup.test.tsx` snapshots every
gallery entry, open, into `__snapshots__/markup.md` and runs the
accessibility scan on each. The entries are in `overlay.gallery.tsx`, ready
for P1-T01.

# Dialogs

One dialog shell and one way to confirm (P1-T07, UN-4316). Import from
`@v1/components/ui/dialog`. The header, footer, Escape and outside-click rules
and focus return come from `@v1/components/ui/overlay` (P1-T08, UN-4315).

## Dialog

- Parts: `Dialog`, `DialogTrigger`, `DialogContent`, `DialogHeader`,
  `DialogBody`, `DialogFooter`, `DialogCancel`.
- `size` on `DialogContent`: `sm` 512 (confirms), `md` 576 (default, forms),
  `lg` 896, `full` (full height, up to 1280). The body scrolls; the header and
  footer stay.
- `open`, `defaultOpen` and `onOpenChange` work as in Radix.
- `busy`: Escape, outside click, Close and Cancel do nothing, and Close and
  Cancel are disabled. Give the primary button `loading`.
- `dismissible` (default true): false keeps the dialog open on an outside
  click; Escape still closes it.
- `beforeClose`: asked before every close; false keeps the dialog open. For
  unsaved changes: `beforeClose={() => !dirty || confirm({ ... })}`.
- Focus is trapped. It starts on the control marked `data-autofocus`, else the
  body's first control, else Close. On close it returns to the opener, or to
  its menu's trigger when a menu item opened it.
- `DialogHeader` takes `titleSize`: `page` 20 (default, forms) or `section`
  16 (confirms, as drawn).
- The dialog is named by the header's title and described by its description.
  Without a description, pass `aria-describedby={undefined}` to
  `DialogContent`.
- A form wraps the body and footer: `<form className="ui:contents">`.
- Footer buttons are `lg` (36), as drawn; `DialogCancel` defaults to it.
- A filled `SearchField` clears on Escape before the dialog closes.

## confirm()

- `await confirm(options)` resolves true or false. `ConfirmHost` mounts
  beside each v1 page, inside its gate, so `details` may use the page's
  session, route and plugins. With no host by the next task, `confirm()`
  resolves false and warns. A confirm is a `role="alertdialog"`.
- `tone`:
  - `standard` (default): `description`, `confirmLabel`.
  - `destructive`: also `consequence` (the red note). The button is the solid
    destructive one, focus starts on Cancel, and an outside click does not
    close it.
  - `blocked`: `reason` instead of a description, only Close, and an optional
    `link` ("Open project") that closes it. Always resolves false.
- Optional: `details` (a panel under the text), `icon` (the header chip;
  destructive defaults to the warning glyph), `confirmIcon`, `cancelLabel`.
- `action`: the dialog stays open and busy until it settles; true then means
  it already ran, so do not run it again. A throw keeps the dialog open, is
  logged and shows in the dialog as an `InlineAlert`, worded by
  `ConfirmHost`'s `describeError` (v1's host uses the API error's message, as
  the toast does).
- While the dialog on screen runs its `action`, every `confirm()` resolves
  false and logs, wherever it is called from. Never call it from an `action`.
- One confirm at a time; the next waits and takes focus when it shows. An
  answer in the first 400 ms after a request shows (the second click of a
  double click) is ignored, and a held Enter or Escape answers only once.

## Tests

`Dialog.test.tsx` and `ConfirmHost.test.tsx` cover behaviour and keyboard
use; `confirm.test.ts` and `useGuardedClose.test.ts` the queue and the close
guard. `markup.test.tsx` snapshots every gallery entry into
`__snapshots__/markup.md` and runs the accessibility scan on each. The entries
are in `dialog.gallery.tsx`, ready for P1-T01.

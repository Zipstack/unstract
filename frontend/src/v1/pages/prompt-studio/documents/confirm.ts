/*
 * ponytail: the shared destructive confirm dialog replaces this; the options
 * are its shape. Until then the browser's own confirm asks with the title and
 * description only (no confirmLabel, no consequence), so frame D08's layout
 * is not drawn here. The swap also moves DocumentsPanel.test.tsx from
 * stubbing window.confirm to answering the dialog.
 */

export type DestructiveConfirm = Readonly<{
  tone: "destructive";
  title: string;
  description: string;
  confirmLabel: string;
  consequence: string;
}>;

export function confirm(options: DestructiveConfirm): Promise<boolean> {
  return Promise.resolve(
    window.confirm(`${options.title}\n\n${options.description}`),
  );
}

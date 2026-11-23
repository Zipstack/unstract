/*
 * ponytail: P1-T07 (UN-4316, dialogs) replaces this with `confirm()` from
 * `@v1/components/ui/dialog`, whose destructive options this takes as they
 * are; swapping the import is the whole change. Until then the browser's own
 * confirm asks, so frame D08's layout is not drawn here.
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

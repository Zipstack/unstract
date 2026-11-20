import { Button } from "@v1/components/ui/button";
import { cn } from "@v1/lib/cn";
import { STATUS_ICONS } from "@v1/lib/icons";
import type { LucideIcon } from "lucide-react";
import { Dialog as RadixDialog } from "radix-ui";
import type { JSX, KeyboardEvent, MouseEvent, ReactNode } from "react";
import type {
  BlockedConfirm,
  ConfirmOptions,
  DestructiveConfirm,
  StandardConfirm,
} from "./confirm";
import {
  Dialog,
  DialogBody,
  DialogCancel,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "./Dialog";

type Tone = NonNullable<ConfirmOptions["tone"]>;

const CHIP_CLASS: Readonly<Record<Tone, string>> = {
  standard: "ui:bg-warning/10 ui:text-warning",
  destructive: "ui:bg-destructive/10 ui:text-destructive",
  blocked: "ui:bg-warning/10 ui:text-warning",
};

function IconChip({ icon: Icon, tone }: { icon: LucideIcon; tone: Tone }) {
  return (
    <div
      className={cn(
        "ui:flex ui:size-8 ui:items-center ui:justify-center ui:rounded-lg",
        CHIP_CLASS[tone],
      )}
    >
      <Icon aria-hidden className="ui:size-4" />
    </div>
  );
}

const ConsequenceIcon = STATUS_ICONS.warning;

/** The text that describes the dialog: what happens, or why it cannot. */
function ConfirmText({ options }: { options: ConfirmOptions }) {
  const blocked = options.tone === "blocked";
  const consequence =
    options.tone === "destructive" ? options.consequence : null;
  return (
    <RadixDialog.Description asChild>
      <div className="ui:flex ui:flex-col ui:gap-3">
        <div>{blocked ? options.reason : options.description}</div>
        {consequence ? (
          <div className="ui:flex ui:items-start ui:gap-2 ui:rounded-md ui:border ui:border-destructive/25 ui:bg-destructive/10 ui:px-3 ui:py-2 ui:text-body-small ui:text-destructive">
            <ConsequenceIcon aria-hidden className="ui:mt-0.5 ui:size-4" />
            <div>{consequence}</div>
          </div>
        ) : null}
      </div>
    </RadixDialog.Description>
  );
}

// The panel under the text, e.g. the items a delete affects.
function Details({ children }: { children?: ReactNode }) {
  return children ? (
    <div className="ui:rounded-lg ui:bg-muted ui:px-4 ui:py-3 ui:text-body-small">
      {children}
    </div>
  ) : null;
}

// A queued request reuses the dialog, so a double click or a held Enter must not answer it unread.
function firstClickOnly(run: () => void) {
  return (event: MouseEvent) => {
    if (event.detail <= 1) {
      run();
    }
  };
}

function ignoreHeldEnter(event: KeyboardEvent): void {
  if (event.repeat && event.key === "Enter") {
    event.preventDefault();
  }
}

type Answer = Readonly<{
  busy: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
}>;

// A destructive action is never the default: focus starts on Cancel.
function ConfirmActions({
  options,
  busy,
  onConfirm,
}: Answer & { options: StandardConfirm | DestructiveConfirm }) {
  const destructive = options.tone === "destructive";
  return (
    <>
      <DialogCancel data-autofocus={destructive || undefined}>
        {options.cancelLabel ?? "Cancel"}
      </DialogCancel>
      <Button
        size="lg"
        variant={destructive ? "destructive" : "primary"}
        leadingIcon={options.confirmIcon}
        loading={busy}
        data-autofocus={destructive ? undefined : true}
        onClick={firstClickOnly(onConfirm)}
      >
        {options.confirmLabel}
      </Button>
    </>
  );
}

function BlockedActions({
  options,
  onDismiss,
}: Pick<Answer, "onDismiss"> & { options: BlockedConfirm }) {
  const { link } = options;
  return (
    <>
      <DialogCancel data-autofocus>
        {options.closeLabel ?? "Close"}
      </DialogCancel>
      {link ? (
        <Button
          size="lg"
          onClick={firstClickOnly(() => {
            onDismiss();
            link.onSelect();
          })}
        >
          {link.label}
        </Button>
      ) : null}
    </>
  );
}

function ConfirmParts({
  options,
  ...answer
}: Answer & { options: ConfirmOptions }) {
  const tone = options.tone ?? "standard";
  const icon =
    options.icon ?? (tone === "destructive" ? STATUS_ICONS.warning : undefined);
  return (
    <>
      <DialogHeader
        title={options.title}
        titleSize="section"
        leading={icon ? <IconChip icon={icon} tone={tone} /> : undefined}
      />
      <DialogBody>
        <ConfirmText options={options} />
        <Details>{options.details}</Details>
      </DialogBody>
      <DialogFooter>
        {options.tone === "blocked" ? (
          <BlockedActions options={options} onDismiss={answer.onDismiss} />
        ) : (
          <ConfirmActions options={options} {...answer} />
        )}
      </DialogFooter>
    </>
  );
}

export type ConfirmDialogProps = Partial<Pick<Answer, "busy">> &
  Omit<Answer, "busy"> &
  Readonly<{
    /** The request on screen; null closes the dialog. */
    options: ConfirmOptions | null;
  }>;

/** A confirm on the dialog shell; a destructive one ignores outside clicks. */
export function ConfirmDialog({
  options,
  busy = false,
  onConfirm,
  onDismiss,
}: ConfirmDialogProps): JSX.Element {
  return (
    <Dialog
      open={options !== null}
      busy={busy}
      dismissible={options?.tone !== "destructive"}
      onOpenChange={(open) => {
        if (!open) {
          onDismiss();
        }
      }}
    >
      <DialogContent
        size="sm"
        data-slot="confirm-dialog"
        onKeyDown={ignoreHeldEnter}
      >
        {options ? (
          <ConfirmParts
            options={options}
            busy={busy}
            onConfirm={onConfirm}
            onDismiss={onDismiss}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

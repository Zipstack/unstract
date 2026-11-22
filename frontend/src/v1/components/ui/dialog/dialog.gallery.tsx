import { Button } from "@v1/components/ui/button";
import { Field, Input } from "@v1/components/ui/form";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { ReactElement } from "react";
import { ConfirmDialog, type ConfirmError } from "./ConfirmDialog";
import type { ConfirmOptions } from "./confirm";
import {
  Dialog,
  DialogBody,
  DialogCancel,
  DialogContent,
  DialogFooter,
  DialogHeader,
  type DialogSize,
  DialogTrigger,
} from "./Dialog";

// Every size, state and confirm variant, each open, for the component gallery.

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

const noop = (): void => undefined;

function SizedDialog({
  size,
  busy = false,
}: {
  size: DialogSize;
  busy?: boolean;
}) {
  return (
    <Dialog defaultOpen busy={busy}>
      <DialogTrigger asChild>
        <Button variant="outline">Open {size}</Button>
      </DialogTrigger>
      <DialogContent size={size}>
        <DialogHeader
          title="Raw log"
          description="File execution 171c7e87 · 24 entries · 2 errors"
        />
        <DialogBody>
          <p className="ui:m-0">The log exactly as the service wrote it.</p>
        </DialogBody>
        <DialogFooter>
          <DialogCancel />
          <Button size="lg" loading={busy}>
            Export
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeploymentFields() {
  return (
    <DialogBody>
      <Field id="g-dialog-name" label="Display name">
        <Input defaultValue="Invoice extraction API" />
      </Field>
      <Field
        id="g-dialog-api"
        label="API name"
        helperText="Lower case, no spaces."
      >
        <Input defaultValue="invoice_extraction" />
      </Field>
    </DialogBody>
  );
}

// A form wraps body and footer; `ui:contents` keeps the panel's column layout.
function FormDialog() {
  return (
    <Dialog defaultOpen beforeClose={() => true}>
      <DialogTrigger asChild>
        <Button>New API deployment</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader
          title="New API deployment"
          description="Turns a workflow into an HTTPS endpoint your systems can post to."
        />
        <form
          className="ui:contents"
          onSubmit={(event) => event.preventDefault()}
        >
          <DeploymentFields />
          <DialogFooter>
            <DialogCancel />
            <Button size="lg" type="submit">
              Create deployment
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const STANDARD: ConfirmOptions = {
  title: "Regenerate the API key?",
  description:
    "A new key is issued immediately and the current one stops working.",
  icon: ACTION_ICONS.refresh,
  confirmLabel: "Regenerate key",
  confirmIcon: ACTION_ICONS.refresh,
};

const DESTRUCTIVE: ConfirmOptions = {
  tone: "destructive",
  title: "Delete “gpt-5.6”?",
  description:
    "This profile is used by 3 workflows. They will fail at run time.",
  consequence: "This cannot be undone.",
  details: (
    <ul className="ui:m-0 ui:list-none ui:p-0">
      <li>Credit Card Parser — ETL Workflow</li>
      <li>IQ-Backoffice-ETL</li>
      <li>Invoice extraction API</li>
    </ul>
  ),
  icon: ACTION_ICONS.delete,
  confirmLabel: "Delete profile",
  confirmIcon: ACTION_ICONS.delete,
};

const BLOCKED: ConfirmOptions = {
  tone: "blocked",
  title: "Invoice Vendor Lookup cannot be deleted",
  reason:
    "This look-up is linked to a Prompt Studio project. Unlink it there first, then delete it here.",
  details: "Linked to 1 project: Invoice Extraction - Webinar",
  link: { label: "Open project", onSelect: noop },
};

function confirmEntry(
  name: string,
  options: ConfirmOptions,
  state: Readonly<{ busy?: boolean; error?: ConfirmError }> = {},
) {
  return {
    name,
    element: (
      <ConfirmDialog
        options={options}
        busy={state.busy}
        error={state.error}
        onConfirm={noop}
        onDismiss={noop}
      />
    ),
  };
}

export const DIALOG_GALLERY: readonly GalleryEntry[] = [
  ...(["sm", "md", "lg", "full"] as const).map((size) => ({
    name: `dialog ${size}`,
    element: <SizedDialog size={size} />,
  })),
  { name: "dialog busy", element: <SizedDialog size="md" busy /> },
  { name: "dialog with a form", element: <FormDialog /> },
  confirmEntry("confirm standard", STANDARD),
  confirmEntry("confirm destructive with details", DESTRUCTIVE),
  confirmEntry("confirm destructive busy", DESTRUCTIVE, { busy: true }),
  confirmEntry("confirm destructive failed", DESTRUCTIVE, {
    error: {
      title: "Something went wrong on our side. Try again.",
      requestId: "a1b2c3d4",
    },
  }),
  confirmEntry("confirm blocked with a link", BLOCKED),
];

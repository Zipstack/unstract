import { IconButton } from "@v1/components/ui/button";
import { ProgressBar } from "@v1/components/ui/feedback";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { PromptDocument } from "@v1/services/promptDocuments";
import type { JSX, ReactNode } from "react";
import { type DocumentState, formatBytes, rowMeta } from "./documentFacts";
import { StatusBadge } from "./StatusBadge";
import type { UploadRow } from "./useUploads";

const FileIcon = ACTION_ICONS.document;

const ROW =
  "ui:flex ui:items-center ui:gap-3 ui:border-t ui:border-border ui:px-5.5 ui:py-3";

function RowShell({
  name,
  children,
  trailing,
}: Readonly<{ name: string; children: ReactNode; trailing: ReactNode }>) {
  return (
    <li className={ROW}>
      <div className="ui:flex ui:size-8.5 ui:shrink-0 ui:items-center ui:justify-center ui:rounded-md ui:bg-muted ui:text-destructive">
        <FileIcon aria-hidden className="ui:size-4" />
      </div>
      <div className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col ui:gap-0.5">
        <p
          className="ui:m-0 ui:truncate ui:text-body-small ui:font-medium ui:text-foreground"
          title={name}
        >
          {name}
        </p>
        {children}
      </div>
      <div className="ui:flex ui:shrink-0 ui:items-center ui:gap-2">
        {trailing}
      </div>
    </li>
  );
}

export type DocumentRowProps = Readonly<{
  document: PromptDocument;
  state: DocumentState;
  onView?: () => void;
  onIndex: () => void;
  onRemove: () => void;
}>;

/** A stored document: name, size · pages, its state and its actions (D04, D07). */
export function DocumentRow({
  document,
  state,
  onView,
  onIndex,
  onRemove,
}: DocumentRowProps): JSX.Element {
  const name = document.document_name;
  const busy = state === "processing";
  return (
    <RowShell
      name={name}
      trailing={
        <>
          <div className="ui:mr-1">
            <StatusBadge state={state} />
          </div>
          {onView ? (
            <IconButton
              icon={ACTION_ICONS.view}
              aria-label={`View ${name}`}
              onClick={onView}
            />
          ) : null}
          <IconButton
            icon={ACTION_ICONS.refresh}
            aria-label={`Index ${name} again`}
            disabled={busy}
            onClick={onIndex}
          />
          <IconButton
            icon={ACTION_ICONS.delete}
            aria-label={`Remove ${name}`}
            disabled={busy}
            onClick={onRemove}
            className="ui:text-destructive ui:not-disabled:hover:text-destructive"
          />
        </>
      }
    >
      <p className="ui:m-0 ui:text-caption ui:text-muted-foreground">
        {rowMeta(document, state)}
      </p>
    </RowShell>
  );
}

/** A file on its way up: a bar and "Uploading · 380 KB of 611 KB" (D06). */
export function UploadingRow({
  row,
}: Readonly<{ row: UploadRow }>): JSX.Element {
  const { file, loaded, started } = row;
  const total = formatBytes(file.size);
  return (
    <RowShell name={file.name} trailing={null}>
      <ProgressBar
        aria-label={`Uploading ${file.name}`}
        value={loaded}
        max={file.size}
        className="ui:max-w-60"
      />
      <p className="ui:m-0 ui:text-caption ui:text-muted-foreground">
        {started
          ? `Uploading · ${formatBytes(Math.min(loaded, file.size))} of ${total}`
          : `Waiting to upload · ${total}`}
      </p>
    </RowShell>
  );
}

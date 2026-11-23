import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
  MenuButton,
} from "@v1/components/ui/menu";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { PromptDocument } from "@v1/services/promptDocuments";
import type { JSX } from "react";
import { documentState, switcherMeta } from "./documentFacts";

export type DocumentSwitcherProps = Readonly<{
  documents: readonly PromptDocument[];
  selectedId: string | null;
  onSelect: (documentId: string) => void;
  indexing: ReadonlySet<string>;
  /** While a run uses the document, switching waits. */
  disabled?: boolean;
}>;

const FileIcon = ACTION_ICONS.document;

/**
 * The viewer's document picker (frame C10): each document with pages · size ·
 * state, the shown one checked, and "1 of 4" beside it.
 */
export function DocumentSwitcher({
  documents,
  selectedId,
  onSelect,
  indexing,
  disabled = false,
}: DocumentSwitcherProps): JSX.Element {
  const index = documents.findIndex(
    (document) => document.document_id === selectedId,
  );
  const selected = index >= 0 ? documents[index] : undefined;
  return (
    <div className="ui:flex ui:min-w-0 ui:items-center ui:gap-3">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <MenuButton
            leadingIcon={FileIcon}
            disabled={disabled || documents.length === 0}
            aria-label={
              selected
                ? `Document: ${selected.document_name}`
                : "Choose a document"
            }
            className="ui:max-w-72 ui:min-w-0"
          >
            <span className="ui:truncate">
              {documents.length === 0
                ? "No documents"
                : (selected?.document_name ?? "Choose a document")}
            </span>
          </MenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="ui:w-72">
          <DropdownMenuRadioGroup
            value={selectedId ?? ""}
            onValueChange={(id) => id !== selectedId && onSelect(id)}
          >
            {documents.map((document) => (
              <DropdownMenuRadioItem
                key={document.document_id}
                value={document.document_id}
                icon={FileIcon}
                description={switcherMeta(
                  document,
                  documentState(document, indexing),
                )}
              >
                {document.document_name}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      {selected ? (
        <span className="ui:shrink-0 ui:text-body-small ui:text-muted-foreground">
          {index + 1} of {documents.length}
        </span>
      ) : null}
    </div>
  );
}

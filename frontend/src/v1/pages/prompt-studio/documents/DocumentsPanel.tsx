import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QueryView } from "@v1/components/patterns/QueryView";
import { Button } from "@v1/components/ui/button";
import { InlineAlert, SkeletonTableRows } from "@v1/components/ui/feedback";
import { ACTION_ICONS } from "@v1/lib/icons";
import {
  type DocumentRef,
  deletePromptDocument,
  type PromptDocument,
  promptDocumentKeys,
  promptDocumentQueries,
  type UploadedDocument,
} from "@v1/services/promptDocuments";
import { type JSX, type ReactNode, useEffect, useMemo, useRef } from "react";
import { confirm } from "./confirm";
import { DocumentRow, UploadingRow } from "./DocumentRows";
import { documentState, failureReason, footerSummary } from "./documentFacts";
import { FileDrop, type FileDropHandle } from "./FileDrop";
import { type PromptCoverage, removalDescription } from "./removal";
import {
  acceptAttribute,
  OSS_UPLOAD_POLICY,
  policyCaption,
  type UploadPolicy,
} from "./uploadPolicy";
import { INDEX_POLL_MS, useIndexing } from "./useIndexing";
import { useUploads } from "./useUploads";

export type DocumentsPanelProps = Readonly<{
  toolId: string;
  /** What uploads may be; the OSS backend's limits unless a distribution passes its own. */
  policy?: UploadPolicy;
  /** Why uploads are refused now, e.g. no default LLM profile; null when they are not. */
  uploadBlockedReason?: string | null;
  /** The prompts' coverage, for the remove confirm's text. */
  prompts?: readonly PromptCoverage[];
  /** Ids the workspace knows are indexing (the socket's `index_document`). */
  indexingIds?: ReadonlySet<string>;
  /** Shows a document in the viewer. */
  onView?: (documentId: string) => void;
  onUploaded?: (document: UploadedDocument) => void;
  /** After a removal, with the ids left. */
  onRemoved?: (documentId: string, remaining: readonly string[]) => void;
  /** The container's own buttons, at the end of the footer (Cancel, Done). */
  footerActions?: ReactNode;
}>;

const SUGGESTION =
  "Try a higher-resolution file, or switch the text extractor in Settings.";
// Without the list the duplicate-name check cannot run, and the backend
// overwrites a stored file before it refuses the duplicate.
const LIST_NOT_LOADED = "Uploads wait for the document list. Retry it first.";
const NO_IDS: ReadonlySet<string> = new Set();
const AddIcon = ACTION_ICONS.add;
const EmptyIcon = ACTION_ICONS.document;

/**
 * Manage Documents (frames D04 to D08): drop or browse, the list with size ·
 * pages and state under the default profile, uploads with progress, parse
 * failures with the extractor's reason, re-index, remove, and a footer. The
 * workspace frame puts it in its Documents tab or dialog.
 */
export function DocumentsPanel(props: DocumentsPanelProps): JSX.Element {
  // Uploads, waits and drafts belong to one tool; another starts afresh.
  return <ToolDocumentsPanel key={props.toolId} {...props} />;
}

function ToolDocumentsPanel({
  toolId,
  policy = OSS_UPLOAD_POLICY,
  uploadBlockedReason = null,
  prompts,
  indexingIds = NO_IDS,
  onView,
  onUploaded,
  onRemoved,
  footerActions,
}: DocumentsPanelProps): JSX.Element {
  const queryClient = useQueryClient();
  const drop = useRef<FileDropHandle | null>(null);
  const indexing = useIndexing(toolId);
  const list = useQuery({
    ...promptDocumentQueries.list(toolId),
    refetchInterval: indexing.ids.size > 0 ? INDEX_POLL_MS : false,
  });
  const documents = list.data ?? [];
  const { settle } = indexing;
  // Each fetch, not each new data: an unchanged list keeps its reference, and
  // a failing one must still let the wait run out.
  // biome-ignore lint/correctness/useExhaustiveDependencies: judged on each fetch
  useEffect(
    () => settle(list.data),
    [list.dataUpdatedAt, list.errorUpdatedAt, settle],
  );

  const busyIds = useMemo(
    () => new Set([...indexing.ids, ...indexingIds]),
    [indexing.ids, indexingIds],
  );
  const names = useMemo(
    () => (list.data ?? []).map((document) => document.document_name),
    [list.data],
  );
  const uploads = useUploads({
    toolId,
    policy,
    existingNames: names,
    onUploaded,
  });

  const remove = useMutation({
    mutationFn: (params: DocumentRef) => deletePromptDocument(params),
    onSuccess: async (_, { documentId }) => {
      await queryClient.invalidateQueries({
        queryKey: promptDocumentKeys.list(toolId),
      });
      onRemoved?.(
        documentId,
        documents
          .map((document) => document.document_id)
          .filter((id) => id !== documentId),
      );
    },
  });

  const askRemove = async (document: PromptDocument) => {
    const ok = await confirm({
      tone: "destructive",
      title: `Remove ${document.document_name}?`,
      description: removalDescription(
        document.document_id,
        documents.length,
        prompts,
      ),
      confirmLabel: "Remove document",
      consequence: "This cannot be undone.",
    });
    if (ok) {
      remove.mutate({ toolId, documentId: document.document_id });
    }
  };

  const blockedReason =
    uploadBlockedReason ?? (list.isSuccess ? null : LIST_NOT_LOADED);

  const failed = documents.filter(
    (document) => documentState(document, busyIds) === "failed",
  );

  return (
    <div data-slot="documents-panel" className="ui:flex ui:min-h-0 ui:flex-col">
      <div className="ui:flex ui:flex-col ui:gap-3 ui:px-5.5 ui:pb-3.5">
        <FileDrop
          ref={drop}
          onFiles={uploads.add}
          accept={acceptAttribute(policy)}
          caption={policyCaption(policy)}
          disabledReason={blockedReason}
        />
        {failed.map((document) => (
          <InlineAlert
            key={document.document_id}
            title={`${document.document_name} could not be parsed`}
            onRetry={() => indexing.request(document)}
          >
            {failureReason(document) ?? "No reason is available."} {SUGGESTION}
          </InlineAlert>
        ))}
      </div>
      <div className="ui:min-h-0 ui:flex-1 ui:overflow-y-auto">
        <QueryView
          query={list}
          loading={<SkeletonTableRows rows={4} columns={1} />}
        >
          {(rows) =>
            rows.length === 0 && uploads.rows.length === 0 ? (
              <EmptyDocuments
                blocked={Boolean(blockedReason)}
                onUpload={() => drop.current?.open()}
              />
            ) : (
              <>
                {/* Frames D06 and D07 drop the heading while a row uploads or failed. */}
                {uploads.rows.length === 0 && failed.length === 0 ? (
                  <div className="ui:flex ui:items-center ui:justify-between ui:px-5.5 ui:pb-2.5">
                    <h3 className="ui:m-0 ui:text-body-small ui:font-semibold ui:text-foreground">
                      Documents{" "}
                      <span className="ui:text-caption ui:font-normal ui:text-muted-foreground">
                        {rows.length}
                      </span>
                    </h3>
                    <Button
                      variant="outline"
                      size="sm"
                      leadingIcon={AddIcon}
                      disabled={Boolean(blockedReason)}
                      onClick={() => drop.current?.open()}
                    >
                      Upload New File
                    </Button>
                  </div>
                ) : null}
                <ul
                  aria-label="Documents"
                  className="ui:m-0 ui:list-none ui:p-0"
                >
                  {uploads.rows.map((row) => (
                    <UploadingRow key={row.key} row={row} />
                  ))}
                  {rows.map((document) => (
                    <DocumentRow
                      key={document.document_id}
                      document={document}
                      state={documentState(document, busyIds)}
                      onView={
                        onView ? () => onView(document.document_id) : undefined
                      }
                      onIndex={() => indexing.request(document)}
                      onRemove={() => void askRemove(document)}
                      removing={
                        remove.isPending &&
                        remove.variables?.documentId === document.document_id
                      }
                    />
                  ))}
                </ul>
              </>
            )
          }
        </QueryView>
      </div>
      <footer className="ui:flex ui:items-center ui:justify-between ui:gap-3 ui:border-t ui:border-border ui:bg-card ui:px-5.5 ui:py-3.5">
        <p
          className="ui:m-0 ui:text-body-small ui:text-muted-foreground"
          aria-live="polite"
        >
          {list.data
            ? footerSummary(list.data, busyIds, uploads.rows.length)
            : null}
        </p>
        {footerActions ? (
          <div className="ui:flex ui:items-center ui:gap-2">
            {footerActions}
          </div>
        ) : null}
      </footer>
    </div>
  );
}

/*
 * ponytail: the core empty state does not exist yet; this is frame D05's
 * markup, to swap for it when it lands.
 */
function EmptyDocuments({
  blocked,
  onUpload,
}: Readonly<{ blocked: boolean; onUpload: () => void }>): JSX.Element {
  return (
    <div className="ui:flex ui:flex-col ui:items-center ui:px-5.5 ui:pt-6 ui:pb-8 ui:text-center">
      <div className="ui:flex ui:size-14 ui:items-center ui:justify-center ui:rounded-xl ui:bg-primary-muted ui:text-primary">
        <EmptyIcon aria-hidden className="ui:size-6" />
      </div>
      <h3 className="ui:m-0 ui:mt-6 ui:text-section-title ui:text-foreground">
        No documents yet
      </h3>
      <p className="ui:m-0 ui:mt-2.5 ui:mb-6.5 ui:max-w-120 ui:text-body ui:text-muted-foreground">
        Prompts run against every document in this list. Add at least one before
        you write a prompt.
      </p>
      <Button
        size="lg"
        leadingIcon={AddIcon}
        disabled={blocked}
        onClick={onUpload}
      >
        Upload documents
      </Button>
    </div>
  );
}

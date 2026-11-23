import { useQuery } from "@tanstack/react-query";
import {
  DocumentViewer,
  type DocumentViewerProps,
} from "@v1/components/patterns/document-viewer/DocumentViewer";
import { QueryView } from "@v1/components/patterns/QueryView";
import { Button } from "@v1/components/ui/button";
import { SkeletonBlock } from "@v1/components/ui/feedback";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@v1/components/ui/navigation";
import { cn } from "@v1/lib/cn";
import { ACTION_ICONS, STATUS_ICONS } from "@v1/lib/icons";
import { ApiError } from "@v1/services/errors";
import {
  type DocumentView,
  type PromptDocument,
  promptDocumentQueries,
} from "@v1/services/promptDocuments";
import { type JSX, type ReactNode, useMemo, useState } from "react";
import { DocumentSwitcher } from "./DocumentSwitcher";
import { documentState, switcherMeta, unavailableMeta } from "./documentFacts";
import { toViewerSource } from "./viewerSource";

/** The highlight slot: filled by the prompt tasks, passed to the viewer as is. */
export type ViewerHighlights = Pick<
  DocumentViewerProps,
  | "highlights"
  | "activeHighlightId"
  | "onHighlightClick"
  | "textHighlights"
  | "onTextHighlightClick"
>;

export type DocumentViewerPaneProps = Readonly<
  {
    toolId: string;
    selectedId: string | null;
    onSelect: (documentId: string) => void;
    /** Opens Manage Documents (the frame's Documents tab or dialog). */
    onManageDocuments: () => void;
    /** Ids the workspace knows are indexing. */
    indexingIds?: ReadonlySet<string>;
    /** While a run uses the shown document, switching waits. */
    switchingDisabled?: boolean;
    /** At the end of the tab row, e.g. the confidence score. */
    tabAccessory?: ReactNode;
  } & ViewerHighlights
>;

const NO_IDS: ReadonlySet<string> = new Set();
const RetryIcon = ACTION_ICONS.refresh;
const WarningIcon = STATUS_ICONS.warning;

const CENTRED =
  "ui:flex ui:h-full ui:min-h-48 ui:flex-col ui:items-center ui:justify-center ui:p-6 ui:text-center";

/**
 * The workspace's document pane (frames C10, C14, D05): the switcher, PDF
 * View and Raw View through the one document viewer, the failed-to-load
 * state, and a footer with pages · size · state.
 */
export function DocumentViewerPane({
  toolId,
  selectedId,
  onSelect,
  onManageDocuments,
  indexingIds = NO_IDS,
  switchingDisabled,
  tabAccessory,
  ...highlights
}: DocumentViewerPaneProps): JSX.Element {
  const [view, setView] = useState<DocumentView>("ORIGINAL");
  const list = useQuery(promptDocumentQueries.list(toolId));
  const documents = list.data ?? [];
  const selected = documents.find(
    (document) => document.document_id === selectedId,
  );
  const content = useQuery({
    ...promptDocumentQueries.content({
      toolId,
      documentId: selected?.document_id ?? "",
      view,
    }),
    enabled: selected !== undefined,
  });
  const source = useMemo(
    () => (content.data ? toViewerSource(content.data) : null),
    [content.data],
  );
  const unrenderable =
    view === "ORIGINAL" &&
    ((content.isError && content.dataUpdatedAt === 0) ||
      (content.isSuccess && source === null));

  let body: ReactNode;
  if (!selected) {
    // A list that failed to load shows its error and Retry, not an empty project.
    body = (
      <QueryView query={list} loading={<SkeletonBlock className="ui:h-full" />}>
        {() => (
          <p
            className={cn(
              CENTRED,
              "ui:m-0 ui:text-body ui:text-muted-foreground",
            )}
          >
            Nothing to preview yet
          </p>
        )}
      </QueryView>
    );
  } else if (unrenderable) {
    body = (
      <FailedToLoad
        onRetry={() => void content.refetch()}
        onRawView={() => setView("EXTRACT")}
      />
    );
  } else if (view === "EXTRACT" && isNotFound(content.error)) {
    body = (
      <p
        className={cn(CENTRED, "ui:m-0 ui:text-body ui:text-muted-foreground")}
      >
        Raw content is not available. Index the document to generate it.
      </p>
    );
  } else {
    body = (
      <QueryView
        query={content}
        loading={<SkeletonBlock className="ui:h-full" />}
      >
        {() => <DocumentViewer source={source} {...highlights} />}
      </QueryView>
    );
  }

  return (
    <section
      aria-label="Document"
      className="ui:flex ui:h-full ui:min-h-0 ui:flex-col ui:rounded-lg ui:border ui:border-border ui:bg-card ui:shadow-sm"
    >
      <header className="ui:flex ui:items-center ui:justify-between ui:gap-2 ui:border-b ui:border-border ui:px-1 ui:py-1.5">
        <DocumentSwitcher
          documents={documents}
          selectedId={selectedId}
          onSelect={onSelect}
          indexing={indexingIds}
          disabled={switchingDisabled}
        />
        <Button variant="ghost" size="sm" onClick={onManageDocuments}>
          Manage Documents
        </Button>
      </header>
      <Tabs
        value={view}
        onValueChange={(value) => setView(value as DocumentView)}
        className="ui:min-h-0 ui:flex-1"
      >
        <div className="ui:flex ui:items-center ui:justify-between ui:gap-3 ui:border-b ui:border-border ui:px-4">
          <TabsList aria-label="Document view">
            <TabsTrigger value="ORIGINAL">PDF View</TabsTrigger>
            <TabsTrigger value="EXTRACT">Raw View</TabsTrigger>
          </TabsList>
          {tabAccessory}
        </div>
        {/* Only the active tab mounts, so one body serves both. */}
        <TabsContent value="ORIGINAL" className="ui:min-h-0 ui:flex-1">
          {body}
        </TabsContent>
        <TabsContent value="EXTRACT" className="ui:min-h-0 ui:flex-1">
          {body}
        </TabsContent>
      </Tabs>
      <footer className="ui:border-t ui:border-border ui:px-4 ui:py-3.5 ui:text-caption ui:text-muted-foreground">
        {footerText(selected, unrenderable, indexingIds)}
      </footer>
    </section>
  );
}

function footerText(
  selected: PromptDocument | undefined,
  unrenderable: boolean,
  indexing: ReadonlySet<string>,
): string {
  if (!selected) {
    return "No document selected";
  }
  return unrenderable
    ? unavailableMeta(selected)
    : switcherMeta(selected, documentState(selected, indexing));
}

const isNotFound = (error: unknown) =>
  error instanceof ApiError && error.status === 404;

/** Frame C14: the file is stored, but there is nothing the viewer can draw. */
function FailedToLoad({
  onRetry,
  onRawView,
}: Readonly<{ onRetry: () => void; onRawView: () => void }>): JSX.Element {
  return (
    <div role="alert" className={CENTRED}>
      <div className="ui:flex ui:size-14 ui:items-center ui:justify-center ui:rounded-xl ui:bg-primary-muted ui:text-primary">
        <WarningIcon aria-hidden className="ui:size-6" />
      </div>
      <h3 className="ui:m-0 ui:mt-6 ui:text-section-title ui:text-foreground">
        Failed to load the document
      </h3>
      <p className="ui:m-0 ui:mt-2.5 ui:mb-6.5 ui:max-w-120 ui:text-body ui:text-muted-foreground">
        The file is stored but the viewer could not render it. Prompts still run
        against the parsed text.
      </p>
      <div className="ui:flex ui:gap-2">
        <Button size="lg" leadingIcon={RetryIcon} onClick={onRetry}>
          Retry
        </Button>
        <Button size="lg" variant="outline" onClick={onRawView}>
          Open Raw View
        </Button>
      </div>
    </div>
  );
}

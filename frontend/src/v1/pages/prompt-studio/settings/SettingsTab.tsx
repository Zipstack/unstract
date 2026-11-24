import { useQuery } from "@tanstack/react-query";
import { useLeaveGuard } from "@v1/components/patterns/form";
import { NoPermission } from "@v1/components/patterns/NoPermission";
import { QueryView } from "@v1/components/patterns/QueryView";
import { InlineAlert } from "@v1/components/ui/feedback";
import { cn } from "@v1/lib/cn";
import { Slot } from "@v1/lib/plugins";
import { registry } from "@v1/plugins";
import { toApiError } from "@v1/services/errors";
import { promptStudioToolQueries } from "@v1/services/promptStudioTool";
import { type JSX, useEffect, useMemo, useState } from "react";
import { AmbleSection } from "./AmbleSection";
import { CustomDataSection } from "./CustomDataSection";
import { GrammarSection } from "./GrammarSection";
import { ProfilesSection } from "./profiles/ProfilesSection";
import { SettingsSection } from "./SettingsSection";
import {
  anchorId,
  type SettingsSection as SectionEntry,
  type SettingsSlotId,
  visibleSections,
} from "./sections";
import { confirmDestructive } from "./standins";

export type SettingsTabProps = Readonly<{
  toolId: string;
  /** Public share: values show, nothing saves. */
  readOnly?: boolean;
  /**
   * Hands the host a check to await before it leaves the tab (another tab,
   * closing the dialog): it asks only while a section has unsaved changes
   * and resolves true when leaving is fine. Closing the browser tab is
   * guarded here. A new `toolId` starts the tab afresh and drops unsaved
   * changes, so the host awaits this check before it switches projects.
   */
  onLeaveGuard?: (canLeave: () => Promise<boolean>) => void;
  /** Whether a plugin fills a cloud section's slot; the plugin registry by default. */
  isSlotFilled?: (slot: SettingsSlotId) => boolean;
}>;

const filledInRegistry = (slot: SettingsSlotId): boolean =>
  registry.slot(slot) !== undefined;

const askDiscard = () =>
  confirmDestructive({
    title: "Discard unsaved settings?",
    description: "Some settings sections have changes that are not saved.",
    confirmLabel: "Discard",
  });

/**
 * The Prompt Studio Settings tab: a section list and one scrollable column of
 * sections, each saving on its own. The project frame (P5-T02) mounts it.
 * Its state belongs to one project: a new `toolId` starts it afresh, so a
 * draft or an open profile editor never carries over to another project.
 */
export function SettingsTab(props: SettingsTabProps): JSX.Element {
  return <ProjectSettings key={props.toolId} {...props} />;
}

function ProjectSettings({
  toolId,
  readOnly = false,
  onLeaveGuard,
  isSlotFilled = filledInRegistry,
}: SettingsTabProps): JSX.Element {
  const sections = visibleSections(isSlotFilled);
  const settings = useQuery(promptStudioToolQueries.detail(toolId));
  const [dirty, setDirty] = useState<ReadonlySet<string>>(new Set());
  // One stable reporter per section, so a section's effect runs only when its own state changes.
  const report = useMemo(() => {
    const reporters = new Map<string, (d: boolean) => void>();
    return (id: string) => {
      const existing = reporters.get(id);
      if (existing) {
        return existing;
      }
      const reporter = (d: boolean) =>
        setDirty((prev) => {
          if (prev.has(id) === d) {
            return prev;
          }
          const next = new Set(prev);
          if (d) {
            next.add(id);
          } else {
            next.delete(id);
          }
          return next;
        });
      reporters.set(id, reporter);
      return reporter;
    };
  }, []);
  const canLeave = useLeaveGuard(dirty.size > 0, askDiscard);
  useEffect(() => onLeaveGuard?.(canLeave), [onLeaveGuard, canLeave]);

  /** A cloud section's slot, when this build shows it. */
  const cloud = (slot: SettingsSlotId) => {
    const section = sections.find((s) => s.slot === slot);
    return section ? (
      <Slot
        id={slot}
        props={{
          toolId,
          readOnly,
          anchorId: anchorId(section.id),
          onDirtyChange: report(section.id),
        }}
        fallback={null}
        failed={
          <FailedSection
            id={section.id}
            label={section.label}
            onDirtyChange={report(section.id)}
          />
        }
      />
    ) : null;
  };

  // A 403 on the project read means no access. A project the user cannot
  // see at all answers 404 (the query is scoped to the user); that case is
  // the project frame's to handle before it mounts this tab.
  if (settings.isError && toApiError(settings.error).kind === "forbidden") {
    return <NoPermission />;
  }

  return (
    <div className="ui:grid ui:min-h-0 ui:grid-cols-[auto_1fr] ui:gap-6">
      <SectionList sections={sections} />
      <div className="ui:grid ui:min-w-0 ui:content-start ui:gap-10 ui:overflow-y-auto">
        <ProfilesSection
          toolId={toolId}
          readOnly={readOnly}
          onDirtyChange={report("llm-profiles")}
        />
        {cloud("prompt-studio.settings.summarized-extraction")}
        {cloud("prompt-studio.settings.llm-challenge")}
        <QueryView query={settings}>
          {(data) => (
            <>
              <CustomDataSection
                settings={data}
                readOnly={readOnly}
                onDirtyChange={report("custom-data")}
              />
              <GrammarSection
                settings={data}
                readOnly={readOnly}
                onDirtyChange={report("grammar")}
              />
              <AmbleSection
                settings={data}
                readOnly={readOnly}
                onDirtyChange={report("preamble")}
              />
            </>
          )}
        </QueryView>
        {cloud("prompt-studio.settings.highlighting")}
      </div>
    </div>
  );
}

/**
 * A cloud section whose plugin failed to load or render. It has nothing left
 * to save, so it clears the section's unsaved flag itself rather than trust
 * a filler that crashed to have done so.
 */
function FailedSection({
  id,
  label,
  onDirtyChange,
}: Readonly<{
  id: string;
  label: string;
  onDirtyChange: (dirty: boolean) => void;
}>): JSX.Element {
  useEffect(() => onDirtyChange(false), [onDirtyChange]);
  return (
    <SettingsSection id={id} title={label}>
      <InlineAlert title={`${label} could not load`}>
        Reload the page to try again.
      </InlineAlert>
    </SettingsSection>
  );
}

function SectionList({
  sections,
}: Readonly<{ sections: readonly SectionEntry[] }>): JSX.Element {
  const [current, setCurrent] = useState(sections[0]?.id);
  return (
    <nav
      aria-label="Settings sections"
      className="ui:w-60 ui:border-r ui:bg-card ui:px-2.5 ui:py-3"
    >
      <ul className="ui:grid ui:gap-0.5">
        {sections.map(({ id, label, icon: Icon }) => (
          <li key={id}>
            <a
              href={`#${anchorId(id)}`}
              aria-current={current === id ? "location" : undefined}
              onClick={() => setCurrent(id)}
              className={cn(
                "ui:group ui:flex ui:h-9 ui:items-center ui:gap-2.5 ui:rounded-md ui:px-2.5 ui:text-body-small ui:font-medium ui:text-foreground ui:no-underline ui:outline-none ui:hover:bg-accent ui:focus-visible:focus-ring",
                current === id &&
                  "ui:bg-primary-muted ui:font-semibold ui:text-primary ui:hover:bg-primary-muted",
              )}
            >
              <Icon
                aria-hidden
                className={cn(
                  "ui:size-4 ui:shrink-0",
                  current === id
                    ? "ui:text-primary"
                    : "ui:text-muted-foreground",
                )}
              />
              {label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

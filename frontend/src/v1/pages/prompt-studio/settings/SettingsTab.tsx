import { useQuery } from "@tanstack/react-query";
import { useLeaveGuard } from "@v1/components/patterns/form";
import { QueryView } from "@v1/components/patterns/QueryView";
import { cn } from "@v1/lib/cn";
import { Slot } from "@v1/lib/plugins";
import { registry } from "@v1/plugins";
import { promptStudioToolQueries } from "@v1/services/promptStudioTool";
import { type JSX, useEffect, useMemo, useState } from "react";
import { AmbleSection } from "./AmbleSection";
import { CustomDataSection } from "./CustomDataSection";
import { GrammarSection } from "./GrammarSection";
import { ProfilesSection } from "./profiles/ProfilesSection";
import {
  anchorId,
  type SettingsSection,
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
   * guarded here.
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
 */
export function SettingsTab({
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
      />
    ) : null;
  };

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

function SectionList({
  sections,
}: Readonly<{ sections: readonly SettingsSection[] }>): JSX.Element {
  const [current, setCurrent] = useState(sections[0]?.id);
  return (
    <nav aria-label="Settings sections" className="ui:w-56 ui:border-r ui:pr-3">
      <ul className="ui:grid ui:gap-1">
        {sections.map((s) => (
          <li key={s.id}>
            <a
              href={`#${anchorId(s.id)}`}
              aria-current={current === s.id ? "location" : undefined}
              onClick={() => setCurrent(s.id)}
              className={cn(
                "ui:flex ui:h-9 ui:items-center ui:rounded-md ui:px-3 ui:text-body ui:text-foreground ui:no-underline ui:outline-none ui:hover:bg-accent ui:focus-visible:focus-ring",
                current === s.id &&
                  "ui:bg-accent ui:font-medium ui:text-primary",
              )}
            >
              {s.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

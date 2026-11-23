import { InlineCode } from "@v1/components/ui/code";
import { type JSX, useId } from "react";

/** The LLM profile behind a model column, as the popover lists it (frame C13). */
export type ProfileFacts = Readonly<{
  name: string;
  llm: string;
  embeddingModel: string;
  vectorDatabase: string;
  textExtractor: string;
  chunkSize: number;
  reindex: boolean;
}>;

export type ProfilePopoverContentProps = Readonly<{ profile: ProfileFacts }>;

/** The popover body; the model column's trigger and Popover belong to the grid. */
export function ProfilePopoverContent({
  profile,
}: ProfilePopoverContentProps): JSX.Element {
  const titleId = useId();
  const rows: readonly [string, string][] = [
    ["LLM", profile.llm],
    ["Embedding Model", profile.embeddingModel],
    ["Vector Database", profile.vectorDatabase],
    ["Text Extractor", profile.textExtractor],
    ["Chunk size", String(profile.chunkSize)],
    ["Reindex", profile.reindex ? "Yes" : "No"],
  ];
  return (
    <section
      data-slot="profile-popover"
      aria-labelledby={titleId}
      className="ui:flex ui:w-75 ui:flex-col ui:text-body-small"
    >
      <header className="ui:flex ui:flex-col ui:gap-0.5 ui:border-b ui:border-border ui:px-4 ui:pt-3.5 ui:pb-2.5">
        <h3
          id={titleId}
          className="ui:m-0 ui:text-body ui:font-semibold ui:text-foreground"
        >
          {profile.name}
        </h3>
        <p className="ui:m-0 ui:text-caption ui:text-muted-foreground">
          LLM profile used by this model column
        </p>
      </header>
      <dl className="ui:m-0">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="ui:flex ui:items-center ui:justify-between ui:gap-2.5 ui:border-b ui:border-border ui:px-4 ui:py-2 ui:last:border-b-0"
          >
            <dt className="ui:text-caption ui:text-muted-foreground">
              {label}
            </dt>
            <dd className="ui:m-0 ui:min-w-0 ui:truncate ui:text-right ui:text-foreground">
              <InlineCode variant="plain" className="ui:text-caption">
                {value}
              </InlineCode>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

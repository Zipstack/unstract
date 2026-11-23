import type { JSX, ReactNode } from "react";
import { anchorId } from "./sections";

/** One section of the Settings tab: heading, optional description, content. */
export function SettingsSection({
  id,
  title,
  description,
  children,
}: Readonly<{
  id: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
}>): JSX.Element {
  const headingId = `${anchorId(id)}-title`;
  return (
    <section
      id={anchorId(id)}
      aria-labelledby={headingId}
      className="ui:grid ui:scroll-mt-4 ui:gap-4"
    >
      <div className="ui:grid ui:gap-1.5">
        <h2
          id={headingId}
          className="ui:text-section-title ui:font-semibold ui:text-foreground"
        >
          {title}
        </h2>
        {description ? (
          <p className="ui:text-body-small ui:text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

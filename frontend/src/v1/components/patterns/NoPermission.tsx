import { Lock } from "lucide-react";
import type { JSX } from "react";

/** Shown instead of a page the signed-in user may not open (admin or platform-admin only). */
export function NoPermission(): JSX.Element {
  return (
    <section
      aria-labelledby="v1-no-permission-title"
      className="ui:flex ui:flex-1 ui:flex-col ui:items-center ui:justify-center ui:gap-3 ui:p-12 ui:text-center"
    >
      <span className="ui:flex ui:size-12 ui:items-center ui:justify-center ui:rounded-lg ui:bg-muted">
        <Lock aria-hidden className="ui:size-6 ui:text-muted-foreground" />
      </span>
      <h1
        id="v1-no-permission-title"
        className="ui:text-section-title ui:font-semibold ui:text-foreground"
      >
        You don't have access to this page
      </h1>
      <p className="ui:max-w-md ui:text-body-small ui:text-muted-foreground">
        Ask an admin of this organisation if you need it.
      </p>
    </section>
  );
}

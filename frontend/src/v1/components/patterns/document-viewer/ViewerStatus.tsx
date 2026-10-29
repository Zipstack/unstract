import type { PdfDocumentState } from "@v1/hooks/usePdfDocument";
import { type FormEvent, useId, useState } from "react";

/** Every state except `ready`, which the page list renders instead. */
export type ViewerStatusState = Exclude<PdfDocumentState, { status: "ready" }>;

export interface ViewerStatusProps {
  state: ViewerStatusState;
  onRetry: () => void;
  onSubmitPassword: (password: string) => void;
}

const panel =
  "ui:flex ui:h-full ui:min-h-48 ui:flex-col ui:items-center ui:justify-center ui:gap-3 ui:p-6 ui:text-center ui:text-body ui:text-muted-foreground";
const title = "ui:text-section-title ui:text-foreground";
const button =
  "ui:inline-flex ui:items-center ui:justify-center ui:rounded-md ui:bg-primary ui:px-4 ui:py-2 ui:text-body ui:text-primary-foreground ui:focus-visible:focus-ring";

/** What the viewer shows while a document loads, fails, or needs a password. */
export function ViewerStatus({
  state,
  onRetry,
  onSubmitPassword,
}: ViewerStatusProps) {
  switch (state.status) {
    case "loading":
      return (
        <output className={panel} aria-live="polite">
          Loading document…
        </output>
      );
    case "empty":
      return (
        <div className={panel}>
          <p className={title}>No document</p>
          <p>There is nothing to show yet.</p>
        </div>
      );
    case "unsupported":
      return (
        <div className={panel} role="alert">
          <p className={title}>This file can't be previewed</p>
          <p>It isn't a PDF, or the PDF is damaged.</p>
        </div>
      );
    case "failed":
      return (
        <div className={panel} role="alert">
          <p className={title}>The document didn't load</p>
          <p>{state.message}</p>
          <button type="button" className={button} onClick={onRetry}>
            Retry
          </button>
        </div>
      );
    case "password":
      return (
        <PasswordPrompt
          incorrect={state.incorrect}
          onSubmit={onSubmitPassword}
        />
      );
  }
}

function PasswordPrompt({
  incorrect,
  onSubmit,
}: {
  incorrect: boolean;
  onSubmit: (password: string) => void;
}) {
  const [password, setPassword] = useState("");
  const inputId = useId();
  const errorId = useId();
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (password !== "") {
      onSubmit(password);
    }
  };
  return (
    <form className={panel} onSubmit={submit}>
      <p className={title}>This document is password-protected</p>
      <label htmlFor={inputId}>Password</label>
      <input
        id={inputId}
        type="password"
        autoComplete="off"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        aria-invalid={incorrect}
        aria-describedby={incorrect ? errorId : undefined}
        className="ui:rounded-md ui:border ui:border-input ui:bg-background ui:px-3 ui:py-2 ui:text-body ui:text-foreground ui:focus-visible:focus-ring"
      />
      {incorrect && (
        <p id={errorId} role="alert" className="ui:text-destructive">
          That password is incorrect.
        </p>
      )}
      <button type="submit" className={button}>
        Open
      </button>
    </form>
  );
}

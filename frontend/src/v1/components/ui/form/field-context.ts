import { createContext, useContext } from "react";

export type FieldContextValue = Readonly<{
  controlId: string;
  /** Ids of the helper and error text that are rendered, space-separated. */
  describedBy: string | undefined;
  invalid: boolean;
  disabled: boolean;
  readOnly: boolean;
}>;

export const FieldContext = createContext<FieldContextValue | null>(null);

/** The enclosing Field, or null for a control used on its own. */
export function useFieldContext(): FieldContextValue | null {
  return useContext(FieldContext);
}

export type FieldControlInput = Readonly<{
  id?: string;
  "aria-describedby"?: string;
  invalid?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
}>;

export type FieldControlState = Readonly<{
  id: string | undefined;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
  invalid: boolean;
  disabled: boolean;
  readOnly: boolean;
}>;

function joinIds(...ids: (string | undefined)[]): string | undefined {
  const joined = ids.filter(Boolean).join(" ");
  return joined === "" ? undefined : joined;
}

/** Resolves a control's id, description, and state: its own props win, then the enclosing Field's. */
export function useFieldControl(props: FieldControlInput): FieldControlState {
  const field = useFieldContext();
  const invalid = props.invalid ?? field?.invalid ?? false;
  return {
    id: props.id ?? field?.controlId,
    "aria-describedby": joinIds(field?.describedBy, props["aria-describedby"]),
    "aria-invalid": invalid ? true : undefined,
    invalid,
    disabled: props.disabled ?? field?.disabled ?? false,
    readOnly: props.readOnly ?? field?.readOnly ?? false,
  };
}

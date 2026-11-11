import { createContext, useContext } from "react";

export type FieldContextValue = Readonly<{
  controlId: string;
  /** The label's id, for controls named by `aria-labelledby` (a radiogroup cannot use `<label for>`). */
  labelId: string;
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
  /** The enclosing Field's label id; undefined outside a Field. */
  labelId: string | undefined;
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

/**
 * Resolves a control's id, description, and state. The enclosing Field's id
 * wins, since its label points at it (set `id` on the Field); otherwise the
 * control's own props win, then the Field's.
 */
export function useFieldControl(props: FieldControlInput): FieldControlState {
  const field = useFieldContext();
  const invalid = props.invalid ?? field?.invalid ?? false;
  return {
    id: field?.controlId ?? props.id,
    labelId: field?.labelId,
    "aria-describedby": joinIds(field?.describedBy, props["aria-describedby"]),
    "aria-invalid": invalid ? true : undefined,
    invalid,
    disabled: props.disabled ?? field?.disabled ?? false,
    readOnly: props.readOnly ?? field?.readOnly ?? false,
  };
}

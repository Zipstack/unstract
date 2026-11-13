import { type AriaAttributes, createContext, useContext } from "react";

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
  /** A spread `aria-invalid` (react-hook-form, a validation library); a true value marks the control invalid. */
  "aria-invalid"?: AriaAttributes["aria-invalid"];
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

/** Joins the given ids into one space-separated list, skipping empty ones. */
export function joinIds(...ids: (string | undefined)[]): string | undefined {
  const joined = ids.filter(Boolean).join(" ");
  return joined === "" ? undefined : joined;
}

/**
 * Resolves a control's id, description, and state. The enclosing Field's id
 * wins, since its label points at it (set `id` on the Field). The description
 * joins the Field's ids, then the control's; for state, the control's own
 * props win, then the Field's. A true `aria-invalid` counts as `invalid`, so
 * the frame and the ARIA state agree.
 */
export function useFieldControl(props: FieldControlInput): FieldControlState {
  const field = useFieldContext();
  const ariaInvalid = props["aria-invalid"];
  const ownInvalid =
    ariaInvalid !== undefined &&
    ariaInvalid !== false &&
    ariaInvalid !== "false"
      ? true
      : props.invalid;
  const invalid = ownInvalid ?? field?.invalid ?? false;
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

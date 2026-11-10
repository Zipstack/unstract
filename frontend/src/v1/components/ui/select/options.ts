import type { ReactNode } from "react";

/** One choice in a Select, Combobox or MultiSelect. */
export type SelectOption = Readonly<{
  value: string;
  label: string;
  description?: string;
  /** A lucide icon or a `<ProviderLogo decorative />`; sized by the row. */
  leading?: ReactNode;
  disabled?: boolean;
  /**
   * Extra words the Combobox and MultiSelect filter matches, e.g. a model id
   * (Select's type-ahead is Radix's own and matches labels only).
   */
  keywords?: readonly string[];
}>;

/**
 * Whether `option` survives the filter `query`: a case-insensitive substring
 * of its label or of any keyword. A blank query matches everything.
 */
export function matchesQuery(option: SelectOption, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle === "") {
    return true;
  }
  return [option.label, ...(option.keywords ?? [])].some((text) =>
    text.toLowerCase().includes(needle),
  );
}

import type { ReactNode } from "react";

/** One choice in a Select, Combobox, MultiSelect or SegmentedControl. */
export type SelectOption = Readonly<{
  value: string;
  label: string;
  description?: string;
  /** A lucide icon or a `<ProviderLogo decorative />`; sized by the row. */
  leading?: ReactNode;
  disabled?: boolean;
  /** Extra words the filter and type-ahead match, e.g. a model id. */
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

/**
 * The index of the next enabled option after `from` (wrapping) whose label
 * starts with `buffer`, ignoring case; `-1` when none does. A buffer of one
 * character repeated ("gg") searches for that character alone, so pressing a
 * letter again cycles through the options starting with it.
 */
export function typeAheadIndex(
  options: readonly SelectOption[],
  buffer: string,
  from: number,
): number {
  const chars = [...buffer.toLowerCase()];
  if (chars.length === 0) {
    return -1;
  }
  const prefix = chars.every((char) => char === chars[0])
    ? chars[0]
    : chars.join("");
  const count = options.length;
  for (let step = 1; step <= count; step++) {
    const index = (((from + step) % count) + count) % count;
    const option = options[index];
    if (!option.disabled && option.label.toLowerCase().startsWith(prefix)) {
      return index;
    }
  }
  return -1;
}

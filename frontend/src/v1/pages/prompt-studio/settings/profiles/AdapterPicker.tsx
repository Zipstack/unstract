import { useQuery } from "@tanstack/react-query";
import {
  SelectField,
  type SelectOption,
} from "@v1/pages/prompt-studio/settings/standins";
import { type AdapterType, adapterQueries } from "@v1/services/adapters";
import type { JSX } from "react";

export type AdapterPickerProps = Readonly<{
  adapterType: Exclude<AdapterType, "OCR">;
  /** The adapter id, or "" for none. */
  value: string;
  onChange: (adapterId: string) => void;
  onBlur?: () => void;
  name?: string;
  placeholder: string;
  /**
   * The saved adapter's name. When the list lacks it (not shared with this
   * user, or retired), it stays as a disabled option so saving other fields
   * keeps it; the backend accepts an unchanged adapter.
   */
  currentName?: string;
}>;

/**
 * Picks one adapter of a type, by id.
 * ponytail: a plain select over `GET adapter/?adapter_type=` until P2-T05's
 * adapter picker lands (search, provider icons, deprecated adapters hidden);
 * it takes these props.
 */
export function AdapterPicker({
  adapterType,
  value,
  onChange,
  onBlur,
  name,
  placeholder,
  currentName,
}: AdapterPickerProps): JSX.Element {
  const adapters = useQuery(adapterQueries.list({ adapterType }));
  const listed: SelectOption[] = (adapters.data ?? []).map((a) => ({
    value: a.id,
    label: a.adapter_name,
  }));
  const missing = value !== "" && !listed.some((o) => o.value === value);
  const options = missing
    ? [
        ...listed,
        {
          value,
          label: currentName ?? value,
          disabled: !adapters.isPending,
        },
      ]
    : listed;
  return (
    <SelectField
      name={name}
      value={value}
      onChange={onChange}
      onBlur={onBlur}
      options={options}
      placeholder={adapters.isError ? "Adapters could not load" : placeholder}
      aria-busy={adapters.isPending || undefined}
    />
  );
}

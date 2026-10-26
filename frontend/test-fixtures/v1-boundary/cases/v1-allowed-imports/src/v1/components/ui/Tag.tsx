import { upper } from "@v1/lib/format";

type TagProps = { label: string };

export function Tag({ label }: TagProps) {
  return <span>{upper(label)}</span>;
}

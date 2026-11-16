import { upper } from "@v1/lib/format";

type TagProps = Readonly<{ label: string }>;

export function Tag({ label }: TagProps) {
  return <span>{upper(label)}</span>;
}

type Props = { width: number; height: number; extra: Record<string, string> };

// One custom property and one plain key: the plain key styles the element.
export function Page({ width, height }: Props) {
  return (
    <div
      className="ui:relative"
      style={{ "--page-aspect": width / height, width }}
    />
  );
}

// A spread hides its keys.
export function Spread({ extra }: Props) {
  return <div style={{ "--page-aspect": 1, ...extra }} />;
}

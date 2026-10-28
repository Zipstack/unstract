type BoxProps = Readonly<{ variant: "outline" | "ghost" }>;

export function Box({ variant }: BoxProps) {
  return (
    <div data-variant={variant}>
      <input type="hidden" />
      <p title="Run #1234">You don't have hidden files</p>
    </div>
  );
}

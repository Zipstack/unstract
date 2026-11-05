type Props = { pageStyle: React.CSSProperties };

// The keys are not visible at the call site, so the attribute is rejected.
export function Page({ pageStyle }: Props) {
  return <div className="ui:relative" style={pageStyle} />;
}

import {
  type BrandMark,
  PRODUCT_MARKS,
  PROVIDER_MARKS,
  type Product,
  REGION_FLAGS,
  type Region,
} from "@v1/assets/marks";
import { cn } from "@v1/lib/cn";
import { CATEGORY_ICONS, type ProviderCategory } from "@v1/lib/icons";
import { iconSource, providerKey } from "@v1/lib/provider";
import { type JSX, useState } from "react";

export type LogoSize = "sm" | "md" | "lg";

const SIZE_CLASS: Readonly<Record<LogoSize, string>> = {
  sm: "ui:size-4",
  md: "ui:size-6",
  lg: "ui:size-10",
};

// A one-ink mark (OpenAI, Anthropic, …) is near-black; flip it on the dark theme.
// The unstract theme has a light surface, so it keeps the mark as drawn.
const MONO_CLASS = "ui:dark:invert";

type MarkImageProps = Readonly<{
  src: string;
  alt: string;
  size: LogoSize;
  mono?: boolean;
  className?: string;
  onError?: () => void;
}>;

function MarkImage({
  src,
  alt,
  size,
  mono,
  className,
  onError,
}: MarkImageProps): JSX.Element {
  return (
    <img
      src={src}
      alt={alt}
      aria-hidden={alt === "" ? true : undefined}
      draggable={false}
      onError={onError}
      className={cn(
        "ui:inline-block ui:shrink-0 ui:object-contain",
        SIZE_CLASS[size],
        mono && MONO_CLASS,
        className,
      )}
    />
  );
}

export type ProviderLogoProps = Readonly<{
  /** Adapter or connector id from the API (`openai|…`), or a bare provider key. */
  provider: string;
  /** Display name; the image's alt text and the fallback initial. */
  name: string;
  /** The API's `icon` field; used when the design has no mark for this provider. */
  icon?: string | null;
  /** Picks the fallback glyph when there is neither a mark nor a usable icon. */
  category?: ProviderCategory;
  size?: LogoSize;
  /** Beside a visible name, the logo adds nothing for a screen reader. */
  decorative?: boolean;
  className?: string;
}>;

/**
 * A provider's logo, from the first source that works: the design's mark,
 * then the API's icon URL, then a fallback (the category glyph, or the name's
 * initial). A source that fails to load is skipped, so every provider renders
 * something, including ones added to the backend later.
 */
export function ProviderLogo({
  provider,
  name,
  icon,
  category,
  size = "md",
  decorative = false,
  className,
}: ProviderLogoProps): JSX.Element {
  const mark: BrandMark | undefined = PROVIDER_MARKS[providerKey(provider)];
  const sources: BrandMark[] = [];
  if (mark) {
    sources.push(mark);
  }
  const url = iconSource(icon);
  if (url && url !== mark?.src) {
    sources.push({ src: url });
  }
  const [failed, setFailed] = useState<ReadonlySet<string>>(() => new Set());
  const source = sources.find((s) => !failed.has(s.src));
  const alt = decorative ? "" : name;

  if (source) {
    return (
      <MarkImage
        src={source.src}
        alt={alt}
        size={size}
        mono={source.mono}
        className={className}
        onError={() => setFailed((prev) => new Set(prev).add(source.src))}
      />
    );
  }

  const Glyph = category ? CATEGORY_ICONS[category] : null;
  const fallbackClass = cn(
    "ui:inline-flex ui:shrink-0 ui:items-center ui:justify-center ui:rounded-sm",
    "ui:bg-muted ui:text-muted-foreground ui:text-caption",
    SIZE_CLASS[size],
    className,
  );
  const content = Glyph ? (
    <Glyph className="ui:size-3/4" aria-hidden="true" />
  ) : (
    name.trim().charAt(0).toUpperCase() || "?"
  );
  if (decorative) {
    return (
      <span aria-hidden="true" data-fallback="true" className={fallbackClass}>
        {content}
      </span>
    );
  }
  return (
    <span
      role="img"
      aria-label={name}
      data-fallback="true"
      className={fallbackClass}
    >
      {content}
    </span>
  );
}

type LabelledMarkProps = Readonly<{
  /** Accessible name; omit when the name is shown beside the mark. */
  label?: string;
  size?: LogoSize;
  className?: string;
}>;

export type ProductMarkProps = LabelledMarkProps &
  Readonly<{ product: Product }>;

/** A product's two-tone mark from the Product Switcher designs. */
export function ProductMark({
  product,
  label,
  size = "md",
  className,
}: ProductMarkProps): JSX.Element {
  const { src } = PRODUCT_MARKS[product];
  return (
    <MarkImage src={src} alt={label ?? ""} size={size} className={className} />
  );
}

export type RegionFlagProps = LabelledMarkProps & Readonly<{ region: Region }>;

/** A region's flag as SVG; emoji flags render as letters on Windows. */
export function RegionFlag({
  region,
  label,
  size = "md",
  className,
}: RegionFlagProps): JSX.Element {
  const { src } = REGION_FLAGS[region];
  return (
    <MarkImage src={src} alt={label ?? ""} size={size} className={className} />
  );
}

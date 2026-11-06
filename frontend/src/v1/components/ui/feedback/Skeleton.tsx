import { cn } from "@v1/lib/cn";
import type { JSX, ReactNode } from "react";

/*
 * Dev spec section 8 and frame 676:9632: muted bars, heights 12 then 10, three
 * widths only (100%, 78%, 46%), never a spinner inside a card. Two values are
 * not tokens, so the closest ones stand in: radius 4 (`rounded-sm`, 6) and the
 * bar colour #e4e4e7 (`muted`).
 */

const BAR = "ui:block ui:rounded-sm ui:bg-muted ui:motion-safe:animate-pulse";
const WIDTHS = ["ui:w-full", "ui:w-[78%]", "ui:w-[46%]"] as const;

export type SkeletonProps = Readonly<{
  /** What is loading, read by screen readers ("Loading projects"). */
  label?: string;
  className?: string;
  children?: ReactNode;
}>;

/**
 * The container every skeleton sits in: one status region whose only text is
 * the label. No `aria-busy`: on a live region it holds announcements until it
 * turns false, and a skeleton unmounts instead, so the label would never be read.
 */
export function Skeleton({
  label = "Loading",
  className,
  children,
}: SkeletonProps): JSX.Element {
  return (
    // biome-ignore lint/a11y/useSemanticElements: <output> may hold only phrasing content, and skeletons hold blocks.
    <div
      role="status"
      data-slot="skeleton"
      className={cn("ui:flex ui:flex-col ui:gap-2.5", className)}
    >
      <span className="ui:sr-only">{label}</span>
      <div aria-hidden className="ui:contents">
        {children}
      </div>
    </div>
  );
}

export type SkeletonTextProps = Readonly<{
  lines?: number;
  className?: string;
}>;

/** Text lines: the first 12 tall, the rest 10, widths cycling 100%, 78%, 46%. */
export function SkeletonText({
  lines = 3,
  className,
}: SkeletonTextProps): JSX.Element {
  return (
    <div
      data-slot="skeleton-text"
      className={cn("ui:flex ui:flex-col ui:gap-2.5", className)}
    >
      {Array.from({ length: lines }, (_, i) => (
        <span
          // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder rows.
          key={i}
          className={cn(
            BAR,
            i === 0 ? "ui:h-3" : "ui:h-2.5",
            WIDTHS[i % WIDTHS.length],
          )}
        />
      ))}
    </div>
  );
}

export type SkeletonBlockProps = Readonly<{ className?: string }>;

/** A block (a card body, a chart, an image); size it with classes. */
export function SkeletonBlock({ className }: SkeletonBlockProps): JSX.Element {
  return (
    <span
      data-slot="skeleton-block"
      className={cn(BAR, "ui:h-24 ui:w-full", className)}
    />
  );
}

export type SkeletonAvatarProps = Readonly<{
  size?: "sm" | "md";
  className?: string;
}>;

export function SkeletonAvatar({
  size = "md",
  className,
}: SkeletonAvatarProps): JSX.Element {
  return (
    <span
      data-slot="skeleton-avatar"
      className={cn(
        BAR,
        "ui:shrink-0 ui:rounded-full",
        size === "sm" ? "ui:size-6" : "ui:size-8",
        className,
      )}
    />
  );
}

export type SkeletonTableRowsProps = Readonly<{
  rows?: number;
  columns?: number;
  className?: string;
}>;

/** Table rows: one 12-tall bar per cell, widths cycling so columns look real. */
export function SkeletonTableRows({
  rows = 5,
  columns = 4,
  className,
}: SkeletonTableRowsProps): JSX.Element {
  return (
    <div
      data-slot="skeleton-table-rows"
      className={cn("ui:flex ui:flex-col", className)}
    >
      {Array.from({ length: rows }, (_, r) => (
        <div
          // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder rows.
          key={r}
          className="ui:flex ui:items-center ui:gap-4 ui:border-b ui:border-border ui:px-4 ui:py-3 ui:last:border-b-0"
        >
          {Array.from({ length: columns }, (_, c) => (
            <span
              // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder cells.
              key={c}
              className="ui:flex ui:flex-1"
            >
              <span
                className={cn(BAR, "ui:h-3", WIDTHS[(r + c) % WIDTHS.length])}
              />
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

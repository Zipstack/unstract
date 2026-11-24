import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import {
  type DragEvent,
  type JSX,
  type Ref,
  useId,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

/*
 * ponytail: the shared file input replaces this drop zone. Keep the seam:
 * `onFiles`, `accept`, `disabledReason` and a handle with `open()`; nothing
 * else here is reused.
 */

export type FileDropHandle = Readonly<{ open: () => void }>;

export type FileDropProps = Readonly<{
  onFiles: (files: File[]) => void;
  /** The picker's `accept`, e.g. ".pdf". */
  accept: string;
  /** The line under the prompt: allowed types and the size limit. */
  caption: string;
  /** Shown instead of the caption while uploads are refused. */
  disabledReason?: string | null;
  ref?: Ref<FileDropHandle>;
}>;

const UploadIcon = ACTION_ICONS.upload;

/** A dashed drop zone that also opens the file picker (frames D04 to D07). */
export function FileDrop({
  onFiles,
  accept,
  caption,
  disabledReason,
  ref,
}: FileDropProps): JSX.Element {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [over, setOver] = useState(false);
  const captionId = useId();
  const promptId = useId();
  const disabled = Boolean(disabledReason);
  useImperativeHandle(
    ref,
    () => ({ open: () => !disabled && inputRef.current?.click() }),
    [disabled],
  );

  const onDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setOver(false);
    if (!disabled) {
      onFiles(Array.from(event.dataTransfer.files));
    }
  };

  return (
    <div
      data-slot="file-drop"
      data-over={over || undefined}
      className={cn(
        "ui:rounded-lg ui:border ui:border-dashed ui:border-border ui:bg-muted ui:data-over:border-primary ui:data-over:bg-primary-muted",
        disabled && "ui:opacity-60",
      )}
    >
      <button
        type="button"
        // aria-disabled, not disabled: a disabled button gets no drop events,
        // and the browser would then open a dropped file in place of the page.
        aria-disabled={disabled || undefined}
        aria-labelledby={promptId}
        aria-describedby={captionId}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(!disabled);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        className="ui:flex ui:w-full ui:cursor-pointer ui:flex-col ui:items-center ui:gap-1.5 ui:rounded-lg ui:px-6 ui:py-5 ui:text-center ui:focus-visible:focus-ring ui:aria-disabled:cursor-not-allowed"
      >
        <span className="ui:flex ui:size-10 ui:items-center ui:justify-center ui:rounded-2xl ui:bg-primary-muted ui:text-muted-foreground">
          <UploadIcon aria-hidden className="ui:size-4.5" />
        </span>
        <span
          id={promptId}
          className="ui:text-body-small ui:font-medium ui:text-foreground"
        >
          Drag &amp; drop files here, or click to browse
        </span>
        <span
          id={captionId}
          className="ui:text-caption ui:text-muted-foreground"
        >
          {disabledReason || caption}
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={accept}
        hidden
        aria-label="Choose files to upload"
        data-testid="file-drop-input"
        onChange={(event) => {
          if (!disabled) {
            onFiles(Array.from(event.target.files ?? []));
          }
          // The same file can be chosen again after a refusal.
          event.target.value = "";
        }}
      />
    </div>
  );
}

import {
  Check,
  ChevronDown,
  Eye,
  EyeOff,
  Search as SearchIcon,
  X,
} from "lucide-react";
import * as React from "react";

import { Checkbox as ShadcnCheckbox } from "@/components/ui/checkbox";
import { Input as ShadcnInput } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverAnchor,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  RadioGroupItem,
  RadioGroup as ShadcnRadioGroup,
} from "@/components/ui/radio-group";
import {
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Select as ShadcnSelect,
  selectContentClassName,
  selectItemClassName,
  selectTriggerClassName,
} from "@/components/ui/select";
import { Switch as ShadcnSwitch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

/**
 * antd-compatible data-entry controls (P3-03): Input (+ TextArea, Password,
 * Search), Select, Checkbox, Switch, Radio, InputNumber.
 *
 * Shim tier per docs/shim-convention.md. The behaviour that a prop swap would
 * lose:
 *   - antd's onChange hands over a DOM event for Input but a raw VALUE for
 *     Select/Switch/Checkbox. Radix inverts several of those. Call-sites are
 *     written against antd's convention, so the shim adapts rather than
 *     rewriting ~90 handlers.
 *   - `Input.TextArea` (14 sites), `Input.Password`, `Input.Search` are
 *     namespaced statics with no Radix equivalent.
 *   - antd `Select` takes `options=[{label,value}]` data; Radix wants composed
 *     children. `Select.Option` children (6 files) are supported too.
 */

/* ------------------------------------------------------------------ Input */

/**
 * antd's `showCount`: a live "N / max" readout under the control.
 *
 * Used on 3 modals (Prompt Studio project description, and both API
 * deployment name fields). Without this it fell into `...props` and vanished,
 * so those fields showed no counter at all while `maxLength` still silently
 * truncated typing — the user hit a limit with nothing telling them why.
 *
 * antd renders the count for both controlled and uncontrolled inputs, so the
 * length is read from `value`/`defaultValue` and kept in sync on change
 * rather than assuming a controlled parent.
 */

/**
 * The antd input surface these shims accept.
 *
 * `showCount` is why this matters and why it is spelled out first: it was
 * passed by call-sites, never destructured, and `...props` swallowed it with
 * no error — the counter simply never rendered. Enumerating the surface turns
 * the next one into a compile error at the call-site rather than a missing
 * feature nobody notices.
 */
type SizeToken = "small" | "middle" | "large";

/** antd hands its change handlers an event-like object, not Radix's value. */
type ChangeEventLike<T> = { target: { value: T } };
type CheckedEventLike = {
  target: { checked: boolean };
  stopPropagation: () => void;
};

interface CountProps {
  /** Renders a live character counter under the control. */
  showCount?: boolean;
  maxLength?: number;
}

interface AntInputProps
  extends Omit<
      React.InputHTMLAttributes<HTMLInputElement>,
      // `size` is a number on the DOM input and a token in antd; `prefix` is
      // the RDFa string attribute on HTMLAttributes and a ReactNode in antd.
      // Both must be dropped before being redeclared below.
      "size" | "prefix"
    >,
    CountProps {
  allowClear?: boolean;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
  size?: SizeToken;
  status?: "error" | "warning";
  bordered?: boolean;
  /**
   * antd v5's replacement for `bordered` ("borderless" | "filled" |
   * "outlined"). Consumed so it cannot reach the DOM as an unknown attribute —
   * Custom Synonyms writes `variant="borderless"` on its word input.
   */
  variant?: string;
}

interface AntTextAreaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement>,
    CountProps {
  /** antd accepts `true` or a { minRows, maxRows } pair. */
  autoSize?: boolean | { minRows?: number; maxRows?: number };
  /** See AntInputProps.variant — EditableText drives prompt VALUES through this. */
  variant?: string;
  /**
   * antd's control size. `<textarea>` has no `size` attribute, so leaving this
   * in `...props` silently stamped `size="small"` on the DOM and the field kept
   * shadcn's 60px floor — 28px taller than the reference, on every prompt.
   */
  size?: "small" | "middle" | "large";
}

interface AntSearchProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  /** Not forwarded to the DOM: the native `size` is a character count. */
  /** Fired on Enter, with the current input value. */
  onSearch?: (value: string) => void;
  size?: SizeToken;
  /**
   * As on AntInputProps. Declared here too because Search does not delegate to
   * InputBase — without it `allowClear` reached the DOM and React warned on
   * every render of the HITL queue search box.
   */
  allowClear?: boolean;
}

interface AntInputNumberProps
  extends Omit<
    React.InputHTMLAttributes<HTMLInputElement>,
    "onChange" | "size"
  > {
  /** antd hands over the numeric VALUE, not the event; null when cleared. */
  onChange?: (value: number | null) => void;
  size?: SizeToken;
}

/** A `{ value, label }` pair, or a `<Select.Option>` supplying the same. */
interface SelectOption {
  value: string | number;
  label?: React.ReactNode;
  /** Renders the option unselectable — Select and Radio.Group both honour it. */
  disabled?: boolean;
}

interface LabelInValue {
  value: string | number;
  label?: React.ReactNode;
}

interface AntSelectProps {
  /** An array under `mode`; a single entry otherwise. */
  value?: string | number | LabelInValue | (string | number | LabelInValue)[];
  defaultValue?: string | number;
  /**
   * Receives the ORIGINAL option value, so non-string values survive — or a
   * `{ value, label }` pair when `labelInValue` is set, as antd does. Under
   * `mode="multiple"`/`"tags"` it is the whole selection as an array, which
   * is the shape every call-site of those modes stores and posts.
   */
  onChange?: (
    value: string | number | LabelInValue | (string | number | LabelInValue)[],
    option?: SelectOption | SelectOption[],
  ) => void;
  options?: SelectOption[];
  placeholder?: React.ReactNode;
  disabled?: boolean;
  allowClear?: boolean;
  /**
   * antd turns the selector into a text box and filters the list as you type.
   * Radix's Select cannot: its keyboard handling is a single-character
   * typeahead over focused items, and an <input> inside its content loses
   * focus the moment the pointer crosses an option. So a `showSearch` select
   * renders as a Popover-anchored combobox instead (see SearchableSelect).
   */
  showSearch?: boolean;
  /**
   * antd's own signature: `(input, option) => boolean`, receiving the OPTION
   * DATA — `{ value, label, ... }` for `options`, or the `<Select.Option>`
   * props for children. Call-sites read whatever field they built the option
   * from (`option.label`, `option.children`, `option.data.label`), so the
   * whole object has to survive: handing over a normalised `{ value, label }`
   * would have made `option.children.toLowerCase()` throw mid-keystroke.
   * `false` disables filtering, as antd allows.
   */
  filterOption?: boolean | ((input: string, option: SelectOption) => boolean);
  /** Which field the DEFAULT filter reads; antd's escape hatch for no filterOption. */
  optionFilterProp?: string;
  /** antd's empty state. Rendered when the search matches nothing. */
  notFoundContent?: React.ReactNode;
  /**
   * antd hands the selection over as `{ value, label }` instead of a bare
   * value, and reads the controlled `value` in that same shape. Configure
   * Connector is written against it — `onChange={(option) =>
   * handleConnectorSelect(option?.value)}` — so ignoring the flag handed that
   * call-site a bare string, `option?.value` came back undefined, and picking
   * a connector did nothing at all.
   */
  labelInValue?: boolean;
  /** Per-option renderer; antd falls back to the option's `label` without it. */
  optionRender?: (option: SelectOption) => React.ReactNode;
  /**
   * Wraps the option list so a call-site can pin its own content below it —
   * Configure Connector's "+ Add new connector" and the Lookup drawer's
   * "Create Lookup" are both rendered this way, and both are the ONLY route
   * to creating one. Dropping the prop left an org with no connectors staring
   * at an empty dropdown with no way out. `dropdownRender` is the pre-5.25
   * spelling of the same prop; the app still uses both.
   */
  popupRender?: (menu: React.ReactNode) => React.ReactNode;
  dropdownRender?: (menu: React.ReactNode) => React.ReactNode;
  /**
   * Both of antd's multi-value modes, neither of which Radix's single-select
   * can express — each renders a purpose-built control instead:
   *
   *   - `tags` is BOTH a chip editor and a picker: the user types a value and
   *     presses Enter, or takes one from the `options` dropdown, and either
   *     way it becomes a removable chip (see TagsInput). Custom Synonyms was
   *     unusable without it — the dropdown opened with no options and no way
   *     to type.
   *   - `multiple` is a fixed-option multi-select with no free text (see
   *     MultiSelect).
   *
   * Both hand `onChange` an ARRAY. That is why neither can quietly fall
   * through to the single-select path: the control looks fine and the value
   * is the wrong shape.
   */
  mode?: "tags" | "multiple";
  /**
   * Caps how many entries the multi-value modes accept. The prompt card's
   * Document Type and Filter Strategy pass 1 to mean "pick exactly one from
   * the list".
   */
  maxCount?: number;
  variant?: string;
  /**
   * Forwarded to the TRIGGER, not to Radix's Root (which renders nothing).
   * Call-sites size these with `style={{ width: 200 }}`, and that was being
   * dropped on the floor.
   */
  style?: React.CSSProperties;
  size?: SizeToken;
  className?: string;
  children?: React.ReactNode;
  /**
   * Forwarded to the TRIGGER, for the same reason as `style` above: `...props`
   * lands on Radix's Root, which renders no DOM, so a test id written at a
   * call-site reached nothing at all.
   */
  "data-testid"?: string;
}

interface AntCheckboxProps {
  checked?: boolean;
  defaultChecked?: boolean;
  /** antd's call-sites read `e.target.checked`, so that shape is rebuilt. */
  onChange?: (e: CheckedEventLike) => void;
  disabled?: boolean;
  className?: string;
  children?: React.ReactNode;
}

interface AntSwitchProps {
  checked?: boolean;
  /**
   * antd accepts `value` as an alias for `checked` (it is what Form.Item
   * injects). SummarizeManager's "Summarize Context" toggle is written
   * `value={isContext}`, so reading only `checked` left the prop to fall into
   * `...props`, land on the DOM, and the switch never reflected its state.
   */
  value?: boolean;
  defaultChecked?: boolean;
  /**
   * antd hands over the new boolean AND the originating click event, unlike
   * Checkbox which hands over an event alone. Card toggles rely on the second
   * argument to stop the click reaching the card behind them.
   */
  onChange?: (
    checked: boolean,
    event: React.MouseEvent<HTMLButtonElement>,
  ) => void;
  disabled?: boolean;
  size?: "small" | "default";
  className?: string;
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
}

interface AntRadioProps {
  value?: string | number;
  disabled?: boolean;
  className?: string;
  children?: React.ReactNode;
  /*
   * Standalone (ungrouped) radios are driven by these, as antd allows. Both
   * handlers are supported because the call-sites are split: Manage Documents
   * and ManageLlmProfiles use onClick, PromptOutput uses onChange.
   */
  checked?: boolean;
  onClick?: (e: React.MouseEvent<HTMLElement>) => void;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  /**
   * Declared explicitly: React's `HTMLAttributes` does not carry `data-*` at
   * all — JSX lets them through on intrinsic elements only — so a call-site
   * passing one is a type error without this line.
   */
  "data-testid"?: string;
}

interface AntRadioGroupProps {
  value?: string | number;
  defaultValue?: string | number;
  onChange?: (e: ChangeEventLike<string>) => void;
  options?: SelectOption[];
  disabled?: boolean;
  className?: string;
  children?: React.ReactNode;
}

interface UseCountLabelArgs extends CountProps {
  value?: unknown;
  defaultValue?: unknown;
  onChange?: React.ChangeEventHandler<HTMLInputElement & HTMLTextAreaElement>;
}

function useCountLabel({
  showCount,
  maxLength,
  value,
  defaultValue,
  onChange,
}: UseCountLabelArgs) {
  const [len, setLen] = React.useState(
    String(value ?? defaultValue ?? "").length,
  );

  // A controlled parent can change `value` without an onChange we saw.
  React.useEffect(() => {
    if (value !== undefined) {
      setLen(String(value ?? "").length);
    }
  }, [value]);

  const handleChange = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement & HTMLTextAreaElement>) => {
      setLen(e.target.value.length);
      onChange?.(e);
    },
    [onChange],
  );

  if (!showCount) {
    return { onChange, label: null };
  }
  return {
    onChange: handleChange,
    label: (
      <div className="ant-input-show-count-suffix mt-1 text-right text-xs text-muted-foreground">
        {maxLength != null ? `${len} / ${maxLength}` : len}
      </div>
    ),
  };
}

const InputBase = React.forwardRef<HTMLInputElement, AntInputProps>(
  function Input(
    {
      allowClear,
      prefix,
      suffix,
      size,
      status,
      bordered,
      variant,
      showCount,
      className,
      ...props
    },
    ref,
  ) {
    const count = useCountLabel({ showCount, ...props });

    const control = (
      <ShadcnInput
        ref={ref}
        className={cn(
          "ant-input",
          size === "small" && "h-8 text-sm",
          size === "large" && "h-11",
          status === "error" && "border-destructive",
          /*
           * antd's `variant="borderless"` drops the border AND the background,
           * so the field reads as plain text until it is focused. EditableText
           * swaps to it whenever a prompt key/value is neither hovered nor
           * being edited — the prop was consumed but never implemented, so
           * every prompt card showed input chrome permanently.
           */
          variant === "borderless" &&
            "border-transparent bg-transparent shadow-none hover:border-input focus-visible:border-input",
          variant === "filled" && "border-transparent bg-muted",
          prefix && "pl-8",
          className,
        )}
        {...props}
        onChange={count.onChange}
      />
    );

    const affixed =
      !prefix && !suffix ? (
        control
      ) : (
        <div className="relative flex items-center">
          {prefix ? (
            <span className="absolute left-2 text-muted-foreground">
              {prefix}
            </span>
          ) : null}
          {control}
          {suffix ? (
            <span className="absolute right-2 cursor-pointer text-muted-foreground">
              {suffix}
            </span>
          ) : null}
        </div>
      );

    if (!count.label) {
      return affixed;
    }
    return (
      <div>
        {affixed}
        {count.label}
      </div>
    );
  },
);

/** antd `<Input.TextArea rows autoSize showCount />`. */
const TextArea = React.forwardRef<HTMLTextAreaElement, AntTextAreaProps>(
  function TextArea(
    { rows = 3, autoSize, showCount, variant, size, className, ...props },
    ref,
  ) {
    const count = useCountLabel({ showCount, ...props });

    /*
     * antd's `autoSize` grows the field to fit its content. Only the OBJECT
     * form ({minRows}) was handled, so `autoSize={true}` — what EditableText
     * passes for every prompt value — fell through to the 3-row default and
     * rendered a 74px box around a single line of text. That surplus repeated
     * per prompt card, which is most of why each cell was ~76px taller than
     * the reference.
     */
    const innerRef = React.useRef<HTMLTextAreaElement | null>(null);
    const setRefs = React.useCallback(
      (node: HTMLTextAreaElement | null) => {
        innerRef.current = node;
        if (typeof ref === "function") {
          ref(node);
        } else if (ref) {
          ref.current = node;
        }
      },
      [ref],
    );

    const autoSizing = autoSize === true || typeof autoSize === "object";
    const minRows =
      typeof autoSize === "object" ? (autoSize.minRows ?? 1) : rows;
    const maxRows = typeof autoSize === "object" ? autoSize.maxRows : undefined;

    const resize = React.useCallback(() => {
      const el = innerRef.current;
      if (!el || !autoSizing) {
        return;
      }
      // Collapse first so the scrollHeight reflects the CURRENT content.
      el.style.height = "auto";
      const line = parseFloat(getComputedStyle(el).lineHeight) || 22;
      const pad =
        parseFloat(getComputedStyle(el).paddingTop) +
        parseFloat(getComputedStyle(el).paddingBottom);
      const min = (typeof autoSize === "object" ? minRows : 1) * line + pad;
      const max = maxRows ? maxRows * line + pad : Infinity;
      el.style.height = `${Math.min(Math.max(el.scrollHeight, min), max)}px`;
    }, [autoSizing, autoSize, minRows, maxRows]);

    React.useLayoutEffect(resize, [resize, props.value]);

    const control = (
      <Textarea
        ref={setRefs}
        onInput={resize}
        rows={
          autoSize === true
            ? 1
            : typeof autoSize === "object"
              ? (autoSize.minRows ?? rows)
              : rows
        }
        className={cn(
          size === "small" && "px-2 py-1 text-sm",
          size === "large" && "px-3 py-2",
          /*
           * shadcn's Textarea carries `min-h-[60px]`, a CSS floor that beats
           * the inline height `resize()` computes, so a one-line prompt
           * measured 60px against the reference's 32px.
           *
           * antd's small autoSize field computes `padding: 0` vertically and
           * floors at 32px instead. Matching those two numbers — rather than
           * just removing the floor — is what puts the box on the reference's
           * height; `py-1` alone lands at 29px.
           */
          autoSizing && size === "small" && "min-h-8 py-0",
          autoSizing && size !== "small" && "min-h-0",
          // See the Input shim: EditableText renders prompt VALUES borderless
          // until they are hovered or edited.
          variant === "borderless" &&
            "border-transparent bg-transparent shadow-none hover:border-input focus-visible:border-input",
          variant === "filled" && "border-transparent bg-muted",
          // The box is sized to its content, so a scrollbar would be dead
          // chrome — unless maxRows caps it.
          autoSizing && !maxRows && "resize-none overflow-hidden",
          className,
        )}
        {...props}
        onChange={count.onChange}
      />
    );

    if (!count.label) {
      return control;
    }
    return (
      <div>
        {control}
        {count.label}
      </div>
    );
  },
);

/** antd `<Input.Password />` with the reveal toggle antd provides. */
const Password = React.forwardRef<
  HTMLInputElement,
  Omit<React.InputHTMLAttributes<HTMLInputElement>, "size">
>(function Password({ className, ...props }, ref) {
  const [show, setShow] = React.useState(false);
  return (
    <div className="relative flex items-center">
      <ShadcnInput
        ref={ref}
        type={show ? "text" : "password"}
        className={cn("pr-9", className)}
        {...props}
      />
      <button
        type="button"
        aria-label={show ? "Hide password" : "Show password"}
        className="absolute right-2 cursor-pointer text-muted-foreground"
        onClick={() => setShow((s) => !s)}
      >
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
});

/** antd `<Input.Search onSearch allowClear />`. */
const Search = React.forwardRef<HTMLInputElement, AntSearchProps>(
  function Search(
    { onSearch, allowClear, className, size: _size, ...props },
    ref,
  ) {
    // antd only draws the clear affordance once there is something to clear.
    const showClear =
      allowClear && props.value !== undefined && props.value !== "";

    return (
      <div className="relative flex items-center">
        <SearchIcon className="absolute left-2 size-4 text-muted-foreground" />
        <ShadcnInput
          ref={ref}
          className={cn("pl-8", showClear && "pr-8", className)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              onSearch?.((e.target as HTMLInputElement).value);
            }
            props.onKeyDown?.(e);
          }}
          {...props}
        />
        {showClear ? (
          <button
            type="button"
            aria-label="Clear"
            className="absolute right-2 cursor-pointer text-muted-foreground hover:text-foreground"
            onClick={() =>
              /*
               * `{ target: { value: "" } }` is the ChangeEventLike shape the
               * other controlled shims in this file emit — enough for a
               * handler reading e.target.value, which is what antd call-sites
               * do, without faking a whole SyntheticEvent.
               */
              props.onChange?.({
                target: { value: "" },
              } as React.ChangeEvent<HTMLInputElement>)
            }
          >
            <X className="size-4" />
          </button>
        ) : null}
      </div>
    );
  },
);

/*
 * Object.assign rather than `Input.TextArea = …`: the statics stay part of
 * the inferred type, so `<Input.TextArea>` type-checks and the
 * shim-completeness guard still finds them by value.
 */
const Input = Object.assign(InputBase, {
  TextArea,
  Password,
  Search,
});

/** antd `<InputNumber min max />`. */
const InputNumber = React.forwardRef<HTMLInputElement, AntInputNumberProps>(
  function InputNumber(
    { onChange, min, max, step, className, size: _size, ...props },
    ref,
  ) {
    return (
      <ShadcnInput
        ref={ref}
        type="number"
        min={min}
        max={max}
        step={step}
        className={className}
        // antd hands the numeric VALUE to onChange, not the event.
        onChange={(e) => {
          const raw = e.target.value;
          onChange?.(raw === "" ? null : Number(raw));
        }}
        {...props}
      />
    );
  },
);

/* ----------------------------------------------------------------- Select */

/**
 * antd `<Select mode="tags">` — a free-text, multi-value chip editor.
 *
 * Radix's Select is single-select over a fixed list of options, so there is no
 * way to express this by configuring it: with `mode` dropped, Custom Synonyms
 * rendered a trigger that opened an EMPTY dropdown with no text input, leaving
 * the feature unusable (a row could be added and its word typed, but never a
 * synonym). This is a purpose-built replacement rather than a Radix wrapper.
 *
 * antd's tags mode is a picker AS WELL as a text box — it still drops down its
 * `options` — and several call-sites lean on the list rather than on free text.
 * Configure Connector's "File types to process" is an enum the user is meant
 * to choose from, and its ArrayField silently drops anything typed that the
 * enum does not contain, so with the options hidden there was no way to fill
 * the field in at all. Same reason for the border: a chip row with no chrome
 * reads as static text rather than as a control, which is how that field and
 * "Folders to process" both looked once `mode` reached here.
 */
function TagsInput({
  value,
  onChange,
  placeholder,
  disabled,
  className,
  style,
  options,
  filterOption,
  optionFilterProp,
  optionRender,
  notFoundContent,
  maxCount,
  "data-testid": testId,
}: {
  value?: string[];
  onChange?: (value: string[]) => void;
  placeholder?: React.ReactNode;
  disabled?: boolean;
  className?: string;
  style?: React.CSSProperties;
  options?: SelectOption[];
  filterOption?: AntSelectProps["filterOption"];
  optionFilterProp?: string;
  optionRender?: (option: SelectOption) => React.ReactNode;
  notFoundContent?: React.ReactNode;
  maxCount?: number;
  "data-testid"?: string;
}) {
  const [draft, setDraft] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);
  // Same `aria-activedescendant` wiring as SearchableSelect and the multiple
  // variant below: the id links the input to the listbox and its options.
  const listId = React.useId();

  const tags = React.useMemo(
    () => (Array.isArray(value) ? value : value == null ? [] : [String(value)]),
    [value],
  );

  const items = React.useMemo(
    () => normaliseOptions(options, undefined),
    [options],
  );
  /** antd stops accepting entries at `maxCount`; the prompt card uses it as "pick one". */
  const full = maxCount != null && tags.length >= maxCount;
  // Chosen options drop out of the list and the draft filters it, as antd does.
  const visible = items.filter(
    (o) =>
      !tags.includes(String(o.value)) &&
      matchesQuery(o, draft, filterOption, optionFilterProp),
  );

  const add = (next: string) => {
    // antd de-duplicates and ignores an empty entry.
    if (!next || tags.includes(next) || full) {
      return;
    }
    onChange?.([...tags, next]);
  };

  const commit = (entry: string) => {
    add(entry);
    setDraft("");
    setActive(0);
  };

  const box = (
    <div
      data-testid={testId}
      style={style}
      className={cn(
        "ant-select-selector flex min-h-8 w-full flex-wrap items-center gap-1 rounded-md border border-input bg-transparent px-2 py-1 focus-within:ring-1 focus-within:ring-ring",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-text",
        className,
      )}
      // antd puts the caret in the box wherever inside it the user clicks; the
      // guard is so a click ON the input keeps the caret where it was put.
      onMouseDown={(event) => {
        if (disabled || event.target === inputRef.current) {
          return;
        }
        event.preventDefault();
        inputRef.current?.focus();
        if (items.length) {
          setOpen(true);
        }
      }}
    >
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs"
        >
          {tag}
          {!disabled && (
            <button
              type="button"
              aria-label={`Remove ${tag}`}
              className="cursor-pointer leading-none opacity-60 hover:opacity-100"
              onClick={() => onChange?.(tags.filter((t) => t !== tag))}
            >
              ×
            </button>
          )}
        </span>
      ))}
      <input
        ref={inputRef}
        type="text"
        className="min-w-24 flex-1 bg-transparent text-sm outline-none"
        placeholder={tags.length ? undefined : (placeholder as string)}
        value={draft}
        disabled={disabled}
        // No `role="combobox"` here, matching the two sibling lists: it would
        // displace the input's implicit `textbox` role, which call-sites and
        // the shim's own tests select it by.
        aria-controls={listId}
        aria-activedescendant={
          open && visible.length ? `${listId}-${active}` : undefined
        }
        onFocus={() => items.length && setOpen(true)}
        onChange={(e) => {
          setDraft(e.target.value);
          setActive(0);
          if (items.length) {
            setOpen(true);
          }
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            // Enter would otherwise submit the surrounding antd Form.
            e.preventDefault();
            // With the list open Enter takes the highlighted option, as antd
            // does; otherwise it commits whatever has been typed.
            commit(
              open && visible[active]
                ? String(visible[active].value)
                : draft.trim(),
            );
          } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            if (!items.length) {
              return;
            }
            e.preventDefault();
            if (!open) {
              setOpen(true);
              return;
            }
            if (visible.length) {
              const step = e.key === "ArrowDown" ? 1 : -1;
              setActive((i) => (i + step + visible.length) % visible.length);
            }
          } else if (e.key === "Escape" && open) {
            e.preventDefault();
            /*
             * Radix listens for Escape on the document, so both this popup and
             * the modal these fields sit in would dismiss on one press. Closing
             * the popup here and stopping the key at the React root leaves the
             * modal open, which is what antd does.
             */
            e.stopPropagation();
            setOpen(false);
          } else if (e.key === "Backspace" && !draft && tags.length) {
            onChange?.(tags.slice(0, -1));
          }
        }}
        // antd also commits the pending entry when focus leaves.
        onBlur={() => commit(draft.trim())}
      />
      {items.length > 0 && (
        <ChevronDown className="ml-auto h-4 w-4 shrink-0 opacity-50" />
      )}
    </div>
  );

  // Free-text-only call-sites (Custom Synonyms, the table headers) have no
  // list to show, and antd renders no dropdown for them either.
  if (!items.length) {
    return box;
  }

  return (
    <Popover open={open && !disabled} onOpenChange={setOpen}>
      <PopoverAnchor asChild>{box}</PopoverAnchor>
      <PopoverContent
        align="start"
        className={cn(
          selectContentClassName,
          "w-[var(--radix-popover-trigger-width)] max-h-[min(16rem,var(--radix-popover-content-available-height))] overflow-y-auto p-1",
        )}
        // The caret belongs in the box — this popup is typed INTO, not tabbed
        // to, and pulling focus out of the input would commit the draft.
        onOpenAutoFocus={(event) => event.preventDefault()}
        onCloseAutoFocus={(event) => event.preventDefault()}
      >
        <div role="listbox" id={listId} aria-multiselectable="true">
          {visible.length === 0 ? (
            <div className="px-2 py-1.5 text-sm text-muted-foreground">
              {notFoundContent ?? "No data"}
            </div>
          ) : (
            visible.map((o, i) => (
              // Options are deliberately not focusable and carry no key handler
              // of their own: this is the `aria-activedescendant` combobox
              // pattern, so focus stays in the draft input and its onKeyDown
              // drives Arrow/Enter into the same `commit` this onClick calls. A
              // handler here would be dead code — the element can never receive
              // the event.
              <div // NOSONAR
                key={String(o.value)}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={false}
                aria-disabled={o.disabled || full || undefined}
                className={cn(
                  selectItemClassName,
                  i === active && "bg-accent text-accent-foreground",
                  (o.disabled || full) && "pointer-events-none opacity-50",
                )}
                onPointerMove={() => setActive(i)}
                // Keep the caret in the box: blurring the input would commit
                // the draft as a tag of its own before this click landed.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => commit(String(o.value))}
              >
                {optionRender ? optionRender(o.data) : o.display}
              </div>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * antd `<Select options onChange>`. antd calls onChange with the VALUE; Radix
 * does too, so the adaptation is mostly about accepting either `options` data
 * or `<Select.Option>` children.
 */
/**
 * One option, split into the three things the shim needs separately:
 * what to RENDER, what to hand CALL-SITES, and what to key Radix on.
 *
 * Keeping `data` verbatim is the load-bearing part. antd passes the option's
 * own props to `filterOption`/`optionRender`, and the call-sites read whatever
 * field they authored: Summarize Manager filters on `option.children`,
 * Adapter Selection on `option.label` (a string it sets ALONGSIDE a rich
 * `children` node), Configure Connector on `option.data.label`. Normalising
 * those into one `{ value, label }` shape made `option.children` undefined and
 * `option.label` a React element — both of which throw on `.toLowerCase()` on
 * the first keystroke, which is worse than not filtering at all.
 */
interface NormalisedOption {
  value: string | number;
  disabled?: boolean;
  /** What the list and the trigger show. */
  display: React.ReactNode;
  /** The option verbatim, as antd hands it to filterOption/optionRender. */
  data: SelectOption;
}

function normaliseOptions(
  options: SelectOption[] | undefined,
  children: React.ReactNode,
): NormalisedOption[] {
  if (options) {
    return options.map((o) => ({
      value: o.value,
      disabled: o.disabled,
      /*
       * antd falls back to the VALUE when an option carries no label, and
       * call-sites rely on it: the prompt card's enforce-type list is built as
       * `{ value: "text" }` with no label at all. Rendering a bare `label`
       * left every item blank, so the trigger showed an empty box instead of
       * the selected type.
       */
      display: o.label ?? String(o.value),
      data: o,
    }));
  }
  return React.Children.toArray(children)
    .filter(
      (
        c,
      ): c is React.ReactElement<
        SelectOption & { children?: React.ReactNode }
      > => React.isValidElement(c),
    )
    .map((c) => ({
      value: c.props.value,
      disabled: c.props.disabled,
      // `<Option label="x">rich node</Option>` renders the node and filters on
      // the label, so display prefers children and `data` keeps both.
      display: c.props.children ?? c.props.label ?? String(c.props.value),
      data: c.props,
    }));
}

/**
 * The multi-value modes' `value`, flattened to plain strings.
 *
 * Stringified because every comparison downstream is `includes`/`===` against
 * an option's value, and those two are routinely different types: `options`
 * carry numeric ids while the stored selection came back from JSON as
 * strings, and `12 === "12"` is false. The object case is `labelInValue`.
 */
function toValueStrings(source: AntSelectProps["value"]): string[] {
  const list = Array.isArray(source)
    ? source
    : source == null || source === ""
      ? []
      : [source];
  return list.map((v) =>
    v != null && typeof v === "object" ? String(v.value) : String(v),
  );
}

/** antd's onChange arguments: `{ value, label }` under labelInValue, else the raw value. */
function toChangeArgs(
  match: NormalisedOption | undefined,
  raw: string,
  labelInValue: boolean | undefined,
): [string | number | LabelInValue, SelectOption | undefined] {
  const selected = match?.value ?? raw;
  return [
    labelInValue ? { value: selected, label: match?.display } : selected,
    match?.data,
  ];
}

/**
 * Flatten an option's renderable content to text, so the DEFAULT filter can
 * match labels that are elements — `<Space><Image/><span>GCS</span></Space>`
 * is the usual shape here, and `String()` on that yields "[object Object]".
 */
function optionText(node: React.ReactNode): string {
  if (node == null || typeof node === "boolean") {
    return "";
  }
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(optionText).join(" ");
  }
  if (React.isValidElement(node)) {
    return optionText((node.props as { children?: React.ReactNode }).children);
  }
  return "";
}

/**
 * antd's filtering: an explicit `filterOption` wins, `false` disables it, and
 * otherwise it is a case-insensitive substring over `optionFilterProp` —
 * falling back to the option's own text, which is what a user typing into
 * these lists is looking at.
 */
function matchesQuery(
  item: NormalisedOption,
  query: string,
  filterOption: AntSelectProps["filterOption"],
  optionFilterProp: string | undefined,
): boolean {
  if (!query) {
    return true;
  }
  if (filterOption === false) {
    return true;
  }
  if (typeof filterOption === "function") {
    return filterOption(query, item.data);
  }
  const field = optionFilterProp
    ? (item.data as Record<string, unknown>)[optionFilterProp]
    : undefined;
  const haystack = optionFilterProp
    ? optionText(field as React.ReactNode)
    : optionText(item.display) || String(item.value);
  return haystack.toLowerCase().includes(query.toLowerCase());
}

interface SearchableSelectProps {
  items: NormalisedOption[];
  /** Already unwrapped from labelInValue and normalised to a string. */
  value?: string;
  placeholder?: React.ReactNode;
  disabled?: boolean;
  size?: SizeToken;
  className?: string;
  style?: React.CSSProperties;
  filterOption?: AntSelectProps["filterOption"];
  optionFilterProp?: string;
  notFoundContent?: React.ReactNode;
  optionRender?: (option: SelectOption) => React.ReactNode;
  renderPopup?: (menu: React.ReactNode) => React.ReactNode;
  onSelect: (item: NormalisedOption) => void;
  /** Honoured so a call-site (or a test) can force the popup open, as antd allows. */
  open?: boolean;
  "data-testid"?: string;
}

/**
 * antd's `showSearch` select: a text box that filters the list as you type.
 *
 * Deliberately NOT Radix's Select. That component owns keyboard focus — it
 * moves DOM focus onto the highlighted option and runs a single-character
 * typeahead on the content — so an <input> nested inside it is unusable: the
 * typeahead swallows the keystrokes, and Select.Item re-focuses itself on
 * every pointermove, stealing the caret the moment the mouse crosses the
 * list. This is the ARIA combobox pattern instead: focus stays in the input
 * for the whole interaction and the active option is tracked with
 * `aria-activedescendant`, which is also what antd does.
 */
const SearchableSelect = React.forwardRef<
  HTMLButtonElement,
  SearchableSelectProps
>(function SearchableSelect(
  {
    items,
    value,
    placeholder,
    disabled,
    size,
    className,
    style,
    filterOption,
    optionFilterProp,
    notFoundContent,
    optionRender,
    renderPopup,
    onSelect,
    open: openProp,
    "data-testid": testId,
  },
  ref,
) {
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(false);
  const open = openProp ?? uncontrolledOpen;
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const listId = React.useId();

  const selected = items.find((o) => String(o.value) === value);
  const visible = items.filter((o) =>
    matchesQuery(o, query, filterOption, optionFilterProp),
  );

  /*
   * Clamp rather than reset: the query changes on every keystroke, and an
   * active index left pointing past the end of the newly filtered list would
   * make Enter a no-op.
   */
  const active = Math.min(activeIndex, Math.max(visible.length - 1, 0));

  const setOpen = (next: boolean) => {
    setUncontrolledOpen(next);
    if (!next) {
      // antd drops the query when the dropdown closes, so reopening shows the
      // full list rather than the last search.
      setQuery("");
    }
  };

  const choose = (item: NormalisedOption | undefined) => {
    if (!item || item.disabled) {
      return;
    }
    onSelect(item);
    setOpen(false);
  };

  const move = (delta: number) => {
    if (!visible.length) {
      return;
    }
    let next = active;
    // Skip disabled rows, and stop rather than wrap once the ends are reached.
    for (let step = 0; step < visible.length; step++) {
      next += delta;
      if (next < 0 || next >= visible.length) {
        return;
      }
      if (!visible[next].disabled) {
        setActiveIndex(next);
        return;
      }
    }
  };

  const menu = (
    <div
      role="listbox"
      id={listId}
      className="max-h-64 overflow-y-auto overflow-x-hidden p-1"
    >
      {visible.length === 0 ? (
        <div className="px-2 py-4 text-center text-sm text-muted-foreground">
          {notFoundContent ?? "No results"}
        </div>
      ) : (
        visible.map((o, i) => (
          // Options are deliberately not focusable and carry no key handler of
          // their own: this is the `aria-activedescendant` combobox pattern, so
          // focus stays on the input and its onKeyDown drives Arrow/Enter into
          // the same `choose` this onClick calls. A handler here would be dead
          // code — the element can never receive the event.
          <div // NOSONAR
            key={String(o.value)}
            id={`${listId}-${i}`}
            role="option"
            aria-selected={String(o.value) === value}
            aria-disabled={o.disabled || undefined}
            className={cn(
              selectItemClassName,
              i === active && "bg-accent text-accent-foreground",
              o.disabled && "pointer-events-none opacity-50",
            )}
            onPointerMove={() => setActiveIndex(i)}
            onClick={() => choose(o)}
          >
            {String(o.value) === value && (
              <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
                <Check className="h-4 w-4" />
              </span>
            )}
            {optionRender ? optionRender(o.data) : o.display}
          </div>
        ))
      )}
    </div>
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          ref={ref}
          type="button"
          role="combobox"
          aria-expanded={open}
          // The listbox this trigger owns. It is only in the tree while the
          // popover is open, which is what `aria-expanded` tells AT.
          aria-controls={listId}
          disabled={disabled}
          data-testid={testId}
          style={style}
          // Radix's Select marks an empty trigger this way and the shared
          // class string greys the placeholder off it.
          data-placeholder={selected ? undefined : ""}
          className={cn(
            selectTriggerClassName,
            "ant-select-selector",
            size === "small" && "h-8 text-sm",
            className,
          )}
        >
          <span className="truncate">{selected?.display ?? placeholder}</span>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className={cn(
          selectContentClassName,
          // The LIST scrolls, not the surface — otherwise the search box
          // scrolls away from the results it is filtering.
          "w-[var(--radix-popover-trigger-width)] max-h-none overflow-hidden p-0",
        )}
        // Focus belongs in the search box, not on the surface Radix would
        // otherwise focus; without this the first keystroke goes nowhere.
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          inputRef.current?.focus();
        }}
      >
        <div className="flex items-center gap-2 border-b px-3">
          <SearchIcon className="h-4 w-4 shrink-0 opacity-50" />
          <input
            ref={inputRef}
            type="text"
            role="searchbox"
            aria-controls={listId}
            aria-activedescendant={
              visible.length ? `${listId}-${active}` : undefined
            }
            className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            placeholder={
              typeof placeholder === "string" ? placeholder : "Search"
            }
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                move(1);
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                move(-1);
              } else if (e.key === "Enter") {
                e.preventDefault();
                choose(visible[active]);
              }
            }}
          />
        </div>
        {/*
         * Same close-on-interaction wrapper as the plain Select path: a
         * `dropdownRender` footer opens a modal, and the popup would sit on
         * top of it. Options close the popup through `choose` already.
         */}
        {/*
         * `presentation`: the wrapper only catches clicks bubbling out of the
         * footer — it carries no semantics of its own, and the elements that
         * do (the listbox below, the footer's buttons) are already reachable.
         */}
        <div role="presentation" onClick={() => setOpen(false)}>
          {renderPopup ? renderPopup(menu) : menu}
        </div>
      </PopoverContent>
    </Popover>
  );
});

/**
 * antd `<Select mode="multiple">` — a fixed-option multi-select.
 *
 * Radix's Select is single-select, and `multiple` used to fall through to the
 * single-select paths below. That failed by SHAPE rather than visibly: the
 * control rendered and looked usable, but handed the call-site one bare value
 * where it expected an array, and offered no way to pick a second entry.
 * Global API Deployment Keys posts that field straight to DRF's
 * `PrimaryKeyRelatedField(many=True)`, which rejected it with
 * `Expected a list of items but got type "str"`.
 *
 * Same `aria-activedescendant` combobox pattern as SearchableSelect (see the
 * note there for why Radix's Select cannot host a search box), with the three
 * differences that are the point of the mode: the popup stays open across
 * selections, the trigger shows the chosen options as removable chips, and
 * the change handler always emits an array.
 *
 * Deliberately NOT the tag editor above: `multiple` has no free text, so
 * routing it there would let a member or a deployment be invented by typing a
 * name matching no option.
 */
interface MultiSelectProps {
  items: NormalisedOption[];
  /** Already unwrapped from labelInValue and stringified, so `includes` works. */
  values: string[];
  onValuesChange: (next: string[]) => void;
  placeholder?: React.ReactNode;
  disabled?: boolean;
  allowClear?: boolean;
  size?: SizeToken;
  className?: string;
  style?: React.CSSProperties;
  filterOption?: AntSelectProps["filterOption"];
  optionFilterProp?: string;
  notFoundContent?: React.ReactNode;
  optionRender?: (option: SelectOption) => React.ReactNode;
  renderPopup?: (menu: React.ReactNode) => React.ReactNode;
  maxCount?: number;
  /** Honoured so a call-site (or a test) can force the popup open, as antd allows. */
  open?: boolean;
  "data-testid"?: string;
}

function MultiSelect({
  items,
  values,
  onValuesChange,
  placeholder,
  disabled,
  allowClear,
  size,
  className,
  style,
  filterOption,
  optionFilterProp,
  notFoundContent,
  optionRender,
  renderPopup,
  maxCount,
  open: openProp,
  "data-testid": testId,
}: MultiSelectProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(false);
  const open = openProp ?? uncontrolledOpen;
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const listId = React.useId();

  const visible = items.filter((o) =>
    matchesQuery(o, query, filterOption, optionFilterProp),
  );
  // Clamped, not reset, for the same reason as SearchableSelect: the query
  // changes on every keystroke and a stale index would make Enter a no-op.
  const active = Math.min(activeIndex, Math.max(visible.length - 1, 0));
  /** antd stops accepting new entries at `maxCount`; removals stay available. */
  const full = maxCount != null && values.length >= maxCount;

  const setOpen = (next: boolean) => {
    /*
     * The one place `disabled` is enforced. A <div> trigger has no `disabled`
     * attribute, and the greyed-out styling below is CSS the pointer obeys but
     * the keyboard does not — so without this, tabbing to a disabled picker
     * and pressing Enter still opened it.
     */
    if (disabled && next) {
      return;
    }
    setUncontrolledOpen(next);
    if (!next) {
      // antd drops the query when the dropdown closes, so reopening shows the
      // full list rather than the last search.
      setQuery("");
    }
  };

  const toggle = (item: NormalisedOption | undefined) => {
    if (!item || item.disabled) {
      return;
    }
    const raw = String(item.value);
    if (values.includes(raw)) {
      onValuesChange(values.filter((v) => v !== raw));
      return;
    }
    if (full) {
      return;
    }
    onValuesChange([...values, raw]);
    /*
     * antd clears the search once an entry is taken but leaves the dropdown
     * open — picking a second option needs neither a reopen nor a manual
     * delete of what was typed for the first.
     */
    setQuery("");
    setActiveIndex(0);
  };

  const move = (delta: number) => {
    if (!visible.length) {
      return;
    }
    let next = active;
    // Skip disabled rows, and stop rather than wrap once the ends are reached.
    for (let step = 0; step < visible.length; step++) {
      next += delta;
      if (next < 0 || next >= visible.length) {
        return;
      }
      if (!visible[next].disabled) {
        setActiveIndex(next);
        return;
      }
    }
  };

  /*
   * A selected value with no matching option still has to render something.
   * These pickers fill their `options` from a fetch, so an edit form seeded
   * with stored ids paints before the list arrives and would otherwise show a
   * row of blank chips.
   */
  const displayFor = (raw: string) =>
    items.find((o) => String(o.value) === raw)?.display ?? raw;

  const remove = (raw: string) =>
    onValuesChange(values.filter((v) => v !== raw));

  const menu = (
    <div
      role="listbox"
      aria-multiselectable="true"
      id={listId}
      className="max-h-64 overflow-y-auto overflow-x-hidden p-1"
    >
      {visible.length === 0 ? (
        <div className="px-2 py-4 text-center text-sm text-muted-foreground">
          {notFoundContent ?? "No results"}
        </div>
      ) : (
        visible.map((o, i) => {
          const raw = String(o.value);
          const checked = values.includes(raw);
          return (
            // Not focusable and no key handler of its own: this is the
            // `aria-activedescendant` pattern, so focus stays in the search
            // box and its onKeyDown drives the same `toggle` this calls.
            <div // NOSONAR
              key={raw}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={checked}
              aria-disabled={o.disabled || (full && !checked) || undefined}
              className={cn(
                selectItemClassName,
                i === active && "bg-accent text-accent-foreground",
                (o.disabled || (full && !checked)) &&
                  "pointer-events-none opacity-50",
              )}
              onPointerMove={() => setActiveIndex(i)}
              onClick={() => toggle(o)}
            >
              {checked && (
                <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
                  <Check className="h-4 w-4" />
                </span>
              )}
              {optionRender ? optionRender(o.data) : o.display}
            </div>
          );
        })
      )}
    </div>
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <div
          role="combobox"
          aria-expanded={open}
          // The listbox this trigger owns. It is only in the tree while the
          // popover is open, which is what `aria-expanded` tells AT.
          aria-controls={listId}
          aria-haspopup="listbox"
          aria-disabled={disabled || undefined}
          tabIndex={disabled ? -1 : 0}
          data-testid={testId}
          style={style}
          // Radix's Select marks an empty trigger this way and the shared
          // class string greys the placeholder off it.
          data-placeholder={values.length ? undefined : ""}
          className={cn(
            selectTriggerClassName,
            /*
             * The shared trigger is a fixed-height, no-wrap single line; a
             * chip row wraps and grows with the selection. The disabled
             * styling is cosmetic — `setOpen` is what actually enforces it.
             */
            "ant-select-selector h-auto min-h-8 flex-wrap justify-start gap-1 whitespace-normal py-1",
            size === "small" && "text-sm",
            disabled && "pointer-events-none opacity-50",
            className,
          )}
          onKeyDown={(event) => {
            /*
             * Radix opens its trigger from a click, and a <div> gets none from
             * the keyboard — so the combobox keys are wired up by hand, or the
             * control is unreachable without a mouse.
             */
            if (
              event.key === "Enter" ||
              event.key === " " ||
              event.key === "ArrowDown"
            ) {
              event.preventDefault();
              setOpen(true);
            }
          }}
        >
          {values.length === 0 ? (
            <span className="truncate">{placeholder}</span>
          ) : (
            values.map((raw) => (
              <span
                key={raw}
                className="inline-flex max-w-full items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs"
              >
                <span className="truncate">{displayFor(raw)}</span>
                {!disabled && (
                  <button
                    type="button"
                    aria-label={`Remove ${optionText(displayFor(raw)) || raw}`}
                    className="cursor-pointer leading-none opacity-60 hover:opacity-100"
                    /*
                     * The chip sits INSIDE the popover trigger, so both events
                     * have to be stopped: mousedown is what Radix opens on,
                     * and the click would reach the trigger behind it.
                     */
                    onMouseDown={(event) => event.stopPropagation()}
                    onClick={(event) => {
                      event.stopPropagation();
                      remove(raw);
                    }}
                  >
                    ×
                  </button>
                )}
              </span>
            ))
          )}
          {allowClear && values.length > 0 && !disabled ? (
            <button
              type="button"
              aria-label="Clear"
              className="ml-auto cursor-pointer opacity-50 hover:opacity-100"
              onMouseDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                onValuesChange([]);
              }}
            >
              <X className="h-4 w-4" />
            </button>
          ) : (
            <ChevronDown className="ml-auto h-4 w-4 shrink-0 opacity-50" />
          )}
        </div>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className={cn(
          selectContentClassName,
          // The LIST scrolls, not the surface — otherwise the search box
          // scrolls away from the results it is filtering.
          "w-[var(--radix-popover-trigger-width)] max-h-none overflow-hidden p-0",
        )}
        // Focus belongs in the search box, not on the surface Radix would
        // otherwise focus; without this the first keystroke goes nowhere.
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          inputRef.current?.focus();
        }}
      >
        <div className="flex items-center gap-2 border-b px-3">
          <SearchIcon className="h-4 w-4 shrink-0 opacity-50" />
          {/*
           * Unconditional, unlike the single-select path which gates on
           * `showSearch`: antd defaults that flag to true in multiple mode, so
           * FileHistoryModal's status filter — which omits the prop — is
           * filterable today and would quietly lose it if this were gated.
           */}
          <input
            ref={inputRef}
            type="text"
            role="searchbox"
            aria-controls={listId}
            aria-activedescendant={
              visible.length ? `${listId}-${active}` : undefined
            }
            className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            placeholder={
              typeof placeholder === "string" ? placeholder : "Search"
            }
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                move(1);
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                move(-1);
              } else if (event.key === "Enter") {
                // Would otherwise submit the antd Form these sit in.
                event.preventDefault();
                toggle(visible[active]);
              } else if (event.key === "Backspace" && !query && values.length) {
                onValuesChange(values.slice(0, -1));
              }
            }}
          />
        </div>
        {/*
         * No close-on-click wrapper here, unlike the two single-select paths:
         * staying open across selections is the whole point of the mode. A
         * `popupRender` footer therefore has to close itself, which no
         * call-site combines with `multiple` today.
         */}
        {renderPopup ? renderPopup(menu) : menu}
      </PopoverContent>
    </Popover>
  );
}

/** antd's multiple-mode onChange arguments: the values ARRAY, plus the options. */
function toMultiChangeArgs(
  raw: string[],
  items: NormalisedOption[],
  labelInValue: boolean | undefined,
): [(string | number | LabelInValue)[], SelectOption[]] {
  const matched = raw.map((r) => items.find((o) => String(o.value) === r));
  return [
    /*
     * The ORIGINAL option value, not the string MultiSelect compares on: a
     * numeric id handed back as "12" is a different value to an API. An entry
     * matching no option keeps its raw string — the options may still be
     * loading (see `displayFor`).
     */
    raw.map((r, i) =>
      labelInValue
        ? { value: matched[i]?.value ?? r, label: matched[i]?.display }
        : (matched[i]?.value ?? r),
    ),
    matched.filter((m): m is NormalisedOption => Boolean(m)).map((m) => m.data),
  ];
}

const SelectBase = React.forwardRef<HTMLButtonElement, AntSelectProps>(
  function Select(
    {
      value,
      defaultValue,
      onChange,
      options,
      placeholder,
      disabled,
      allowClear,
      showSearch,
      filterOption,
      optionFilterProp,
      notFoundContent,
      labelInValue,
      optionRender,
      popupRender,
      dropdownRender,
      mode,
      maxCount,
      // antd styling prop; consumed so it cannot land on the DOM
      variant,
      size,
      className,
      style,
      children,
      "data-testid": testId,
      ...props
    },
    ref,
  ) {
    /*
     * Only consulted when a popup renderer is supplied — see the SelectContent
     * below for why that case has to drive `open` itself. Declared up here
     * because the tags-mode return below is an early exit.
     */
    const [popupOpen, setPopupOpen] = React.useState(false);

    /*
     * Free-text multi-value entry; Radix's Select cannot express it.
     *
     * ONLY `tags`. antd's `multiple` is a fixed-option multi-select over
     * `options` with NO free text, and its call-sites (GroupMemberManager,
     * FileHistoryModal, Global API Deployment Keys) pick from a known list —
     * routing them here would let a member, a file status or a deployment be
     * invented by typing one. They go to MultiSelect below instead.
     */
    if (mode === "tags") {
      return (
        <TagsInput
          value={toValueStrings(value)}
          onChange={(next) => onChange?.(next)}
          placeholder={placeholder}
          disabled={disabled}
          className={className}
          style={style}
          options={options}
          filterOption={filterOption}
          optionFilterProp={optionFilterProp}
          optionRender={optionRender}
          notFoundContent={notFoundContent}
          maxCount={maxCount}
          data-testid={testId}
        />
      );
    }

    const items = normaliseOptions(options, children);

    /*
     * antd's fixed-option multi-select. Placed ahead of both single-select
     * paths below because falling through to them is not a degraded picker,
     * it is the wrong VALUE: they call onChange with one bare entry where the
     * call-site holds — and posts — an array.
     */
    if (mode === "multiple") {
      return (
        <MultiSelect
          items={items}
          // `toMultiChangeArgs` restores the original value type on the way
          // back out, so the stringification stops at this boundary.
          values={toValueStrings(value ?? defaultValue)}
          onValuesChange={(next) =>
            onChange?.(...toMultiChangeArgs(next, items, labelInValue))
          }
          placeholder={placeholder}
          disabled={disabled}
          allowClear={allowClear}
          size={size}
          className={className}
          style={style}
          filterOption={filterOption}
          optionFilterProp={optionFilterProp}
          notFoundContent={notFoundContent}
          optionRender={optionRender}
          renderPopup={popupRender ?? dropdownRender}
          maxCount={maxCount}
          open={(props as { open?: boolean }).open}
          data-testid={testId}
        />
      );
    }

    /*
     * antd treats "" as "nothing selected" and shows the placeholder; several
     * call-sites seed their state with `useState("")`. Radix reserves the
     * empty string internally, so passing it through leaves the trigger blank
     * AND suppresses the placeholder. Map it back to undefined.
     */
    const toValue = (v: AntSelectProps["value"]) => {
      /*
       * Under `labelInValue` the call-site holds `{ value, label }`, and
       * `String()`-ing that yields "[object Object]", which matches no item:
       * the trigger went blank AND suppressed the placeholder, so a selected
       * connector looked like no selection at all.
       */
      const raw =
        labelInValue && v != null && typeof v === "object" && !Array.isArray(v)
          ? v.value
          : v;
      // An array only reaches here if a call-site passes one without a `mode`;
      // antd shows nothing in that case, and Radix would throw on a non-string.
      return raw == null || raw === "" || Array.isArray(raw)
        ? undefined
        : String(raw);
    };

    // `dropdownRender` is what antd called this before 5.25; both are in use.
    const renderPopup = popupRender ?? dropdownRender;

    const optionItems = items.map((o) => (
      <SelectItem
        key={String(o.value)}
        value={String(o.value)}
        disabled={o.disabled}
      >
        {optionRender ? optionRender(o.data) : o.display}
      </SelectItem>
    ));

    if (showSearch) {
      return (
        <SearchableSelect
          ref={ref}
          items={items}
          value={toValue(value) ?? toValue(defaultValue)}
          placeholder={placeholder}
          disabled={disabled}
          size={size}
          className={className}
          style={style}
          filterOption={filterOption}
          optionFilterProp={optionFilterProp}
          notFoundContent={notFoundContent}
          optionRender={optionRender}
          renderPopup={renderPopup}
          onSelect={(item) =>
            onChange?.(...toChangeArgs(item, String(item.value), labelInValue))
          }
          open={(props as { open?: boolean }).open}
          data-testid={testId}
        />
      );
    }

    return (
      <ShadcnSelect
        value={toValue(value)}
        defaultValue={toValue(defaultValue)}
        onValueChange={(v) => {
          /*
           * Radix reserves "" and rejects a `SelectItem` carrying it, so this
           * can never be a user selection — it is Radix announcing its own
           * uncontrolled-to-controlled switch. `toValue` maps antd's "nothing
           * selected" to undefined, which leaves Radix uncontrolled until a
           * real value arrives; forwarding the "" it then emits wrote that
           * emptiness straight back over the value that had just landed.
           *
           * Prompt Studio's Limit-to Section blanked out on every edit for
           * exactly this: the profile's "Default" reached the field and was
           * wiped in the same tick.
           */
          if (v === "") {
            return;
          }
          const match = items.find((o) => String(o.value) === v);
          onChange?.(...toChangeArgs(match, v, labelInValue));
        }}
        disabled={disabled}
        {...(renderPopup
          ? { open: popupOpen, onOpenChange: setPopupOpen }
          : {})}
        {...props}
      >
        <SelectTrigger
          ref={ref}
          /*
           * `style` and `data-testid` belong on the TRIGGER, not on Radix's
           * Root (which renders nothing) — call-sites size these with
           * `style={{ width: 200 }}`, and the trigger is what a test clicks.
           */
          style={style}
          data-testid={testId}
          className={cn(
            "ant-select-selector",
            size === "small" && "h-8 text-sm",
            className,
          )}
        >
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {renderPopup ? (
            /*
             * antd closes its dropdown the moment focus leaves the select, so
             * a footer button inside `dropdownRender` closes it as a side
             * effect. Radix has no equivalent, and both call-sites open a
             * modal from that footer — leaving the popup open would park it on
             * top of the very modal it just opened. Close on `click` rather
             * than `mousedown`: unmounting the button mid-mousedown would eat
             * the click before the footer's own handler ever ran.
             *
             * `presentation` keeps this passive wrapper from breaking the
             * listbox/option relationship Radix sets up around it.
             */
            <div role="presentation" onClick={() => setPopupOpen(false)}>
              {renderPopup(<>{optionItems}</>)}
            </div>
          ) : (
            optionItems
          )}
        </SelectContent>
      </ShadcnSelect>
    );
  },
);

/** antd `<Select.Option>` — data holder consumed by Select above. */
function Option({
  children,
}: {
  value?: string | number;
  children?: React.ReactNode;
}) {
  return children ?? null;
}

const Select = Object.assign(SelectBase, { Option });

/* --------------------------------------------------- Checkbox / Switch */

/**
 * antd `<Checkbox checked onChange>` gives onChange a DOM-like event with
 * `target.checked`; Radix gives a boolean. Call-sites read `e.target.checked`,
 * so the shim rebuilds that shape.
 */
const Checkbox = React.forwardRef<HTMLButtonElement, AntCheckboxProps>(
  function Checkbox(
    {
      checked,
      defaultChecked,
      onChange,
      disabled,
      className,
      children,
      ...props
    },
    ref,
  ) {
    const box = (
      <ShadcnCheckbox
        ref={ref}
        checked={checked}
        defaultChecked={defaultChecked}
        disabled={disabled}
        onCheckedChange={(next) =>
          onChange?.({
            target: { checked: next === true },
            stopPropagation: () => undefined,
          })
        }
        className={className}
        {...props}
      />
    );
    if (!children) {
      return box;
    }
    return (
      <Label className="flex items-center gap-2 font-normal">
        {box}
        {children}
      </Label>
    );
  },
);

/**
 * antd `<Switch checked onChange>` — onChange receives `(checked, event)`.
 *
 * onChange is driven off the Root's own `onClick`, NOT off Radix's
 * `onCheckedChange`. Radix routes that through `useControllableState`, which
 * invokes the callback from inside a state updater — i.e. during the following
 * render, after the click has finished bubbling. A handler written
 * `(checked, e) => e.stopPropagation()` (both card toggles are) would then run
 * too late to stop anything. Reading `aria-checked` off the button gives the
 * pre-toggle state for controlled and uncontrolled switches alike, and a
 * `<button>` turns keyboard activation into a click, so both input paths work.
 */
const Switch = React.forwardRef<HTMLButtonElement, AntSwitchProps>(
  function Switch(
    {
      checked,
      value,
      defaultChecked,
      onChange,
      onClick,
      disabled,
      size,
      className,
      ...props
    },
    ref,
  ) {
    return (
      <ShadcnSwitch
        ref={ref}
        checked={checked ?? value}
        defaultChecked={defaultChecked}
        disabled={disabled}
        onClick={(event) => {
          onClick?.(event);
          onChange?.(
            event.currentTarget.getAttribute("aria-checked") !== "true",
            event,
          );
        }}
        className={cn(size === "small" && "scale-90", className)}
        {...props}
      />
    );
  },
);

/* ------------------------------------------------------------------ Radio */

/*
 * Marks that a Radio is inside a Radio.Group.
 *
 * antd allows a STANDALONE `<Radio checked onClick />` — Manage Documents and
 * the LLM-profiles settings table both render one per row, with no group, to
 * pick the active document/profile. Radix's RadioGroupItem cannot do that: it
 * reads its group's context and throws
 * "`RadioGroupItemProvider` must be used within `RadioGroup`", which took down
 * the whole route via the error boundary — the reported "clicking Settings /
 * Manage Documents throws error".
 *
 * So the shim has to cover both shapes: grouped items go to Radix, ungrouped
 * ones render a native input that honours `checked`/`onClick` directly.
 */
const InRadioGroupContext = React.createContext(false);

const RadioBase = React.forwardRef<HTMLButtonElement, AntRadioProps>(
  function Radio(
    {
      value,
      disabled,
      className,
      children,
      checked,
      onClick,
      onChange,
      ...props
    },
    ref,
  ) {
    const inGroup = React.useContext(InRadioGroupContext);

    return (
      <Label
        className={cn(
          /*
           * INLINE-flex, as antd's .ant-radio-wrapper is. A block-level `flex`
           * spans the full cell, so a label-less radio (the "Select Default"
           * column renders one per row) pinned itself to the left edge and
           * ignored the cell's `text-align: center` — it sat 39px off from its
           * own centred column header.
           */
          "ant-radio-wrapper inline-flex items-center gap-2 font-normal",
          !disabled && "cursor-pointer",
          className,
        )}
      >
        {inGroup ? (
          <RadioGroupItem
            ref={ref}
            value={String(value)}
            disabled={disabled}
            {...props}
          />
        ) : (
          /*
           * Standalone: a native radio, styled to match the Radix one. `name`
           * is deliberately omitted — these are independent single radios, and
           * sharing a name would make the browser deselect its siblings.
           */
          <input
            type="radio"
            className="size-4 shrink-0 cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-50"
            checked={checked ?? false}
            disabled={disabled}
            onClick={onClick}
            // React requires onChange on a controlled input; forward the
            // caller's when there is one so PromptOutput's radio still fires.
            onChange={onChange ?? (() => undefined)}
            {...props}
          />
        )}
        {children}
      </Label>
    );
  },
);

/** antd `<Radio.Group value onChange>` — onChange gets an event-like object. */
const RadioGroup = React.forwardRef<HTMLDivElement, AntRadioGroupProps>(
  function RadioGroup(
    {
      value,
      defaultValue,
      onChange,
      options,
      disabled,
      className,
      children,
      ...props
    },
    ref,
  ) {
    return (
      <ShadcnRadioGroup
        ref={ref}
        value={value != null ? String(value) : undefined}
        defaultValue={defaultValue != null ? String(defaultValue) : undefined}
        disabled={disabled}
        onValueChange={(v) => onChange?.({ target: { value: v } })}
        className={cn("ant-radio-group flex flex-col gap-2", className)}
        {...props}
      >
        {/* Tells descendant Radios they may use Radix's RadioGroupItem. */}
        <InRadioGroupContext.Provider value={true}>
          {options
            ? options.map((o) => (
                <Radio
                  key={String(o.value)}
                  value={o.value}
                  disabled={o.disabled}
                >
                  {o.label}
                </Radio>
              ))
            : children}
        </InRadioGroupContext.Provider>
      </ShadcnRadioGroup>
    );
  },
);

const Radio = Object.assign(RadioBase, {
  Group: RadioGroup,
  // antd renders Radio.Button as a segmented control; the call-sites here
  // only rely on it behaving as a radio, so it maps to the same component.
  Button: RadioBase,
});

export { Checkbox, Input, InputNumber, Radio, Select, Switch };

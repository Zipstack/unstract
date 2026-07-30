import { Eye, EyeOff, Search as SearchIcon } from "lucide-react";
import * as React from "react";

import { Checkbox as ShadcnCheckbox } from "@/components/ui/checkbox";
import { Input as ShadcnInput } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
}

interface AntTextAreaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement>,
    CountProps {
  /** antd accepts `true` or a { minRows, maxRows } pair. */
  autoSize?: boolean | { minRows?: number; maxRows?: number };
}

interface AntSearchProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  /** Not forwarded to the DOM: the native `size` is a character count. */
  /** Fired on Enter, with the current input value. */
  onSearch?: (value: string) => void;
  size?: SizeToken;
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
  /** Radio.Group forwards this to the individual radio. */
  disabled?: boolean;
}

interface AntSelectProps {
  value?: string | number | string[];
  defaultValue?: string | number;
  /** Receives the ORIGINAL option value, so non-string values survive. */
  onChange?: (
    value: string | number | string[],
    option?: SelectOption,
  ) => void;
  options?: SelectOption[];
  placeholder?: React.ReactNode;
  disabled?: boolean;
  allowClear?: boolean;
  showSearch?: boolean;
  /**
   * antd's `tags` mode is a FREE-TEXT multi-value input: the user types a
   * value, presses Enter, and it becomes a removable chip. Radix's Select is
   * single-select over a fixed option list and cannot express this at all, so
   * tags mode renders a dedicated chip editor instead (see TagsInput below).
   * Custom Synonyms is the only call-site, and it was unusable without this:
   * the dropdown opened with no options and no way to type.
   */
  mode?: "tags" | "multiple";
  variant?: string;
  size?: SizeToken;
  className?: string;
  children?: React.ReactNode;
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
  /** antd hands over a plain boolean here, unlike Checkbox. */
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  size?: "small" | "default";
  className?: string;
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
    { rows = 3, autoSize, showCount, className, ...props },
    ref,
  ) {
    const count = useCountLabel({ showCount, ...props });

    const control = (
      <Textarea
        ref={ref}
        rows={typeof autoSize === "object" ? (autoSize.minRows ?? rows) : rows}
        className={className}
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

/** antd `<Input.Search onSearch />`. */
const Search = React.forwardRef<HTMLInputElement, AntSearchProps>(
  function Search({ onSearch, className, size: _size, ...props }, ref) {
    return (
      <div className="relative flex items-center">
        <SearchIcon className="absolute left-2 size-4 text-muted-foreground" />
        <ShadcnInput
          ref={ref}
          className={cn("pl-8", className)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              onSearch?.((e.target as HTMLInputElement).value);
            }
            props.onKeyDown?.(e);
          }}
          {...props}
        />
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
 */
function TagsInput({
  value,
  onChange,
  placeholder,
  disabled,
  className,
}: {
  value?: string[];
  onChange?: (value: string[]) => void;
  placeholder?: React.ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  const [draft, setDraft] = React.useState("");
  const tags = React.useMemo(
    () => (Array.isArray(value) ? value : value == null ? [] : [String(value)]),
    [value],
  );

  const commit = () => {
    const next = draft.trim();
    // antd de-duplicates and ignores an empty entry.
    if (next && !tags.includes(next)) {
      onChange?.([...tags, next]);
    }
    setDraft("");
  };

  return (
    <div
      className={cn(
        "flex min-h-8 flex-wrap items-center gap-1 rounded-md px-2 py-1",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
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
        type="text"
        className="min-w-24 flex-1 bg-transparent text-sm outline-none"
        placeholder={tags.length ? undefined : (placeholder as string)}
        value={draft}
        disabled={disabled}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            // Enter would otherwise submit the surrounding antd Form.
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && !draft && tags.length) {
            onChange?.(tags.slice(0, -1));
          }
        }}
        // antd also commits the pending entry when focus leaves.
        onBlur={commit}
      />
    </div>
  );
}

/**
 * antd `<Select options onChange>`. antd calls onChange with the VALUE; Radix
 * does too, so the adaptation is mostly about accepting either `options` data
 * or `<Select.Option>` children.
 */
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
      mode,
      // antd styling prop; consumed so it cannot land on the DOM
      variant,
      size,
      className,
      children,
      ...props
    },
    ref,
  ) {
    // Free-text multi-value entry; Radix's Select cannot express it.
    if (mode === "tags" || mode === "multiple") {
      return (
        <TagsInput
          value={
            Array.isArray(value)
              ? value
              : value == null
                ? []
                : [String(value)]
          }
          onChange={(next) => onChange?.(next)}
          placeholder={placeholder}
          disabled={disabled}
          className={className}
        />
      );
    }

    const items =
      options ??
      React.Children.toArray(children)
        .filter(
          (
            c,
          ): c is React.ReactElement<
            SelectOption & { children?: React.ReactNode }
          > => React.isValidElement(c),
        )
        .map((c) => ({
          value: c.props.value,
          label: c.props.children ?? c.props.label,
        }));

    /*
     * antd treats "" as "nothing selected" and shows the placeholder; several
     * call-sites seed their state with `useState("")`. Radix reserves the
     * empty string internally, so passing it through leaves the trigger blank
     * AND suppresses the placeholder. Map it back to undefined.
     */
    const toValue = (v: string | number | string[] | undefined) =>
      // An array only reaches here if a call-site passes one without a `mode`;
      // antd shows nothing in that case, and Radix would throw on a non-string.
      v == null || v === "" || Array.isArray(v) ? undefined : String(v);

    return (
      <ShadcnSelect
        value={toValue(value)}
        defaultValue={toValue(defaultValue)}
        onValueChange={(v) => {
          // Hand back the original (possibly non-string) option value.
          const match = items.find((o) => String(o.value) === v);
          onChange?.(match?.value ?? v, match);
        }}
        disabled={disabled}
        {...props}
      >
        <SelectTrigger
          ref={ref}
          className={cn(
            "ant-select-selector",
            size === "small" && "h-8 text-sm",
            className,
          )}
        >
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {items.map((o) => (
            <SelectItem key={String(o.value)} value={String(o.value)}>
              {/*
               * antd falls back to the VALUE when an option carries no label,
               * and call-sites rely on it: the prompt card's enforce-type list
               * is built as `{ value: "text" }` with no label at all. Rendering
               * a bare `label` left every item blank, so the trigger showed an
               * empty box instead of the selected type.
               */}
              {o.label ?? String(o.value)}
            </SelectItem>
          ))}
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

/** antd `<Switch checked onChange>` — onChange receives a boolean. */
const Switch = React.forwardRef<HTMLButtonElement, AntSwitchProps>(
  function Switch(
    {
      checked,
      value,
      defaultChecked,
      onChange,
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
        onCheckedChange={(next) => onChange?.(next)}
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
          "ant-radio-wrapper flex items-center gap-2 font-normal",
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

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
function useCountLabel({ showCount, maxLength, value, defaultValue, onChange }) {
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
    (e) => {
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

const Input = React.forwardRef(function Input(
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
          <span className="absolute left-2 text-muted-foreground">{prefix}</span>
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
});

/** antd `<Input.TextArea rows autoSize showCount />`. */
const TextArea = React.forwardRef(function TextArea(
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
});

/** antd `<Input.Password />` with the reveal toggle antd provides. */
const Password = React.forwardRef(function Password(
  { className, ...props },
  ref,
) {
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
const Search = React.forwardRef(function Search(
  { onSearch, className, ...props },
  ref,
) {
  return (
    <div className="relative flex items-center">
      <SearchIcon className="absolute left-2 size-4 text-muted-foreground" />
      <ShadcnInput
        ref={ref}
        className={cn("pl-8", className)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            onSearch?.(e.target.value);
          }
          props.onKeyDown?.(e);
        }}
        {...props}
      />
    </div>
  );
});

Input.TextArea = TextArea;
Input.Password = Password;
Input.Search = Search;

/** antd `<InputNumber min max />`. */
const InputNumber = React.forwardRef(function InputNumber(
  { onChange, min, max, step, className, ...props },
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
});

/* ----------------------------------------------------------------- Select */

/**
 * antd `<Select options onChange>`. antd calls onChange with the VALUE; Radix
 * does too, so the adaptation is mostly about accepting either `options` data
 * or `<Select.Option>` children.
 */
const Select = React.forwardRef(function Select(
  {
    value,
    defaultValue,
    onChange,
    options,
    placeholder,
    disabled,
    allowClear,
    showSearch,
    size,
    className,
    children,
    ...props
  },
  ref,
) {
  const items =
    options ??
    React.Children.toArray(children)
      .filter(Boolean)
      .map((c) => ({
        value: c.props?.value,
        label: c.props?.children ?? c.props?.label,
      }));

  return (
    <ShadcnSelect
      value={value != null ? String(value) : undefined}
      defaultValue={defaultValue != null ? String(defaultValue) : undefined}
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
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </ShadcnSelect>
  );
});

/** antd `<Select.Option>` — data holder consumed by Select above. */
Select.Option = function Option({ children }) {
  return children ?? null;
};

/* --------------------------------------------------- Checkbox / Switch */

/**
 * antd `<Checkbox checked onChange>` gives onChange a DOM-like event with
 * `target.checked`; Radix gives a boolean. Call-sites read `e.target.checked`,
 * so the shim rebuilds that shape.
 */
const Checkbox = React.forwardRef(function Checkbox(
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
});

/** antd `<Switch checked onChange>` — onChange receives a boolean. */
const Switch = React.forwardRef(function Switch(
  { checked, defaultChecked, onChange, disabled, size, className, ...props },
  ref,
) {
  return (
    <ShadcnSwitch
      ref={ref}
      checked={checked}
      defaultChecked={defaultChecked}
      disabled={disabled}
      onCheckedChange={(next) => onChange?.(next)}
      className={cn(size === "small" && "scale-90", className)}
      {...props}
    />
  );
});

/* ------------------------------------------------------------------ Radio */

const Radio = React.forwardRef(function Radio(
  { value, disabled, className, children, ...props },
  ref,
) {
  return (
    <Label
      className={cn(
        "ant-radio-wrapper flex items-center gap-2 font-normal",
        className,
      )}
    >
      <RadioGroupItem
        ref={ref}
        value={String(value)}
        disabled={disabled}
        {...props}
      />
      {children}
    </Label>
  );
});

/** antd `<Radio.Group value onChange>` — onChange gets an event-like object. */
Radio.Group = React.forwardRef(function RadioGroup(
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
      {options
        ? options.map((o) => (
            <Radio key={String(o.value)} value={o.value} disabled={o.disabled}>
              {o.label}
            </Radio>
          ))
        : children}
    </ShadcnRadioGroup>
  );
});

Radio.Button = Radio;

export { Checkbox, Input, InputNumber, Radio, Select, Switch };

import { CircleHelp } from "lucide-react";
import * as React from "react";
import {
  Controller,
  FormProvider,
  type UseFormReturn,
  useForm,
  useFormContext,
  useWatch,
} from "react-hook-form";

import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * antd-compatible `Form` (P3-01/P3-02) implemented on react-hook-form.
 *
 * This is the highest-risk conversion in the migration: antd's Form bundles
 * validation, layout and state into one component, and the codebase drives it
 * imperatively through a form instance — `form.setFieldsValue()`,
 * `form.validateFields()`, `form.resetFields()` (14 `useForm()` sites, 102
 * `Form.Item`s). Rewriting each call-site by hand would mean 102 chances to
 * change submit or validation behaviour.
 *
 * So the antd surface is preserved:
 *   - `Form.useForm()` returns a form instance exposing antd's imperative API
 *   - `<Form form={} layout="vertical" onFinish={}>`
 *   - `<Form.Item name label rules>` wrapping a single controlled child
 *
 * Under the hood it is react-hook-form, so the shadcn primitives receive the
 * usual `value`/`onChange` and validation state renders as inline messages,
 * exactly as antd did.
 */

/**
 * The antd Form surface these shims accept.
 *
 * This file is the strongest case for typing the layer. Four of these props
 * were MISSING and fell into `...props`, each failing silently:
 *
 *   - `onValuesChange` — handlers mirroring the form into state never ran, so
 *     Save posted an empty body and looked like it did nothing
 *   - `setFields` — six modals called it and got
 *     `TypeError: form.setFields is not a function` on the first keystroke
 *   - `initialValues` — fields were never seeded
 *   - `validateStatus` / `help` — the backend's 400 message landed on a DOM
 *     div instead of being displayed
 *
 * Naming each one means the next omission is a compile error at the call-site,
 * not a defect a user has to report.
 */

/** antd's NamePath: a string, or an array for nested fields. */
type NamePath = string | Array<string | number>;

interface AntdRule {
  required?: boolean;
  message?: string;
  max?: number;
  min?: number;
  pattern?: RegExp;
  /** antd hands (rule, value); rejecting marks the field invalid. */
  validator?: (rule: unknown, value: unknown) => Promise<unknown> | unknown;
}

/** One entry of antd's `form.setFields([...])`. */
interface FieldData {
  name?: NamePath;
  value?: unknown;
  /** An empty array clears the error; a non-empty one sets it. */
  errors?: string[];
}

type FormValues = Record<string, unknown>;

/** The instance returned by `Form.useForm()`. */
interface FormInstance {
  /** Escape hatch to the underlying react-hook-form methods. */
  __methods: UseFormReturn<FormValues>;
  setFieldsValue: (values?: FormValues) => void;
  setFieldValue: (name: NamePath, value: unknown) => void;
  getFieldsValue: () => FormValues;
  getFieldValue: (name: NamePath) => unknown;
  /** Resolves with the values, REJECTS when invalid, as antd does. */
  validateFields: () => Promise<FormValues>;
  setFields: (fields?: FieldData[]) => void;
  resetFields: () => void;
  submit: () => void;
  isFieldsTouched: () => boolean;
  getFieldsError: () => Array<[string, unknown]>;
}

interface AntFormProps
  extends Omit<React.FormHTMLAttributes<HTMLFormElement>, "onSubmit"> {
  form?: FormInstance;
  layout?: "horizontal" | "vertical" | "inline";
  onFinish?: (values: FormValues) => void;
  onFinishFailed?: (errors: unknown) => void;
  /** Applied ON MOUNT ONLY, matching antd. */
  initialValues?: FormValues;
  onValuesChange?: (changed: FormValues, all: FormValues) => void;
}

interface FormItemProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "children"> {
  name?: NamePath;
  label?: React.ReactNode;
  rules?: AntdRule[];
  required?: boolean;
  /** `checked` for switches and checkboxes, `value` otherwise. */
  valuePropName?: string;
  /**
   * antd's per-item seed, the sibling of `<Form initialValues>`. Distinct from
   * "no value": a checkbox seeded `false` must read as `false`, because
   * call-sites branch on `=== false` to tell "unchecked" from "not yet loaded".
   */
  initialValue?: unknown;
  /**
   * antd's hint beside the label: a bare node, or `{ title, icon }` to pick a
   * different marker. Rendered as an icon that reveals `title` on hover/focus.
   */
  tooltip?:
    | React.ReactNode
    | { title?: React.ReactNode; icon?: React.ReactNode };
  /** antd's server-error channel, paired with `help`. */
  validateStatus?: "error" | "warning" | "success" | "validating";
  help?: React.ReactNode;
  /** antd's always-on hint below the control, independent of `help`. */
  extra?: React.ReactNode;
  children?: React.ReactNode;
}

/** Translate antd `rules` into RHF's validate/required options. */
function toRules(rules: AntdRule[] = [], label?: React.ReactNode) {
  const out: Record<string, unknown> = {};
  for (const rule of rules) {
    if (rule?.required) {
      out.required = rule.message ?? `${label ?? "This field"} is required`;
    }
    if (rule?.max != null) {
      out.maxLength = {
        value: rule.max,
        message: rule.message ?? `Max ${rule.max}`,
      };
    }
    if (rule?.min != null) {
      out.minLength = {
        value: rule.min,
        message: rule.message ?? `Min ${rule.min}`,
      };
    }
    if (rule?.pattern) {
      out.pattern = {
        value: rule.pattern,
        message: rule.message ?? "Invalid format",
      };
    }
    if (typeof rule?.validator === "function") {
      const validator = rule.validator;
      const existing = (out.validate ?? {}) as Record<string, unknown>;
      out.validate = {
        ...existing,
        [`custom${Object.keys(existing).length}`]: async (value: unknown) => {
          try {
            await validator({}, value);
            return true;
          } catch (e) {
            return (
              (e instanceof Error ? e.message : undefined) ??
              rule.message ??
              "Invalid value"
            );
          }
        },
      };
    }
  }
  return out;
}

/**
 * antd's `Form.useForm()`. Returns `[form]`, where `form` carries the
 * imperative methods the existing call-sites already use.
 */
function useAntdForm(): [FormInstance] {
  const methods = useForm({ mode: "onSubmit", shouldUnregister: false });

  const instance = React.useMemo(
    () => ({
      __methods: methods,

      /** antd: set one or many fields. */
      setFieldsValue: (values: FormValues = {}) => {
        for (const [k, v] of Object.entries(values)) {
          methods.setValue(k, v, { shouldDirty: false, shouldValidate: false });
        }
      },
      // These take a NamePath too, so they get the same normalisation the
      // Form.Item name does.
      setFieldValue: (name: NamePath, value: unknown) =>
        methods.setValue(toFieldName(name) as string, value, {
          shouldDirty: true,
        }),

      getFieldsValue: () => methods.getValues(),
      getFieldValue: (name: NamePath) =>
        methods.getValues(toFieldName(name) as string),

      /**
       * antd resolves with the values and REJECTS when invalid — call-sites do
       * `await form.validateFields().catch(() => null)`, so the rejection has
       * to be preserved or invalid forms would submit.
       */
      validateFields: async () => {
        const ok = await methods.trigger();
        if (!ok) {
          // antd rejects with an error carrying `errorFields`, and call-sites
          // read it, so the shape is declared rather than bolted on untyped.
          const err: Error & { errorFields?: unknown[] } = new Error(
            "Validation failed",
          );
          err.errorFields = Object.entries(methods.formState.errors).map(
            ([name, e]) => ({ name: [name], errors: [e?.message] }),
          );
          throw err;
        }
        return methods.getValues();
      },

      /**
       * antd's `setFields([{ name, errors, value }])`.
       *
       * Six modals call this from their `onValuesChange` handler to clear the
       * error on the field being edited — New Workflow, API Deployment (both
       * variants), ETL Task, Notifications, LLM Profile and the Prompt Studio
       * project modal. It was missing entirely, so those handlers would throw
       * `TypeError: form.setFields is not a function` on the first keystroke.
       */
      setFields: (fields: FieldData[] = []) => {
        for (const field of fields) {
          const name = toFieldName(field?.name);
          if (!name) {
            continue;
          }
          if ("value" in field) {
            methods.setValue(name, field.value, { shouldDirty: true });
          }
          // antd clears an error with `errors: []` and sets one with a
          // non-empty array.
          const errors = field?.errors;
          if (Array.isArray(errors)) {
            if (errors.length) {
              methods.setError(name, { type: "server", message: errors[0] });
            } else {
              methods.clearErrors(name);
            }
          }
        }
      },

      resetFields: () => methods.reset({}),
      submit: () => methods.handleSubmit(() => undefined)(),
      isFieldsTouched: () => methods.formState.isDirty,
      getFieldsError: () => Object.entries(methods.formState.errors),
    }),
    [methods],
  );

  return [instance];
}

/**
 * antd's seed order: `initialValues` first, then whatever the store already
 * holds on top. `undefined` entries are skipped so a field RHF has merely
 * registered — value not yet supplied — doesn't blank out its initial value.
 */
function mergeOverInitialValues(
  initialValues: FormValues,
  current: FormValues,
): FormValues {
  const merged: FormValues = { ...initialValues };
  for (const [key, value] of Object.entries(current ?? {})) {
    if (value !== undefined) {
      merged[key] = value;
    }
  }
  return merged;
}

/** antd `<Form form layout onFinish initialValues onValuesChange>`. */
const FormBase = React.forwardRef<HTMLFormElement, AntFormProps>(function Form(
  {
    form,
    layout = "horizontal",
    onFinish,
    onFinishFailed,
    initialValues,
    onValuesChange,
    name,
    className,
    children,
    ...props
  },
  ref,
) {
  // Support both a supplied instance and an uncontrolled form.
  const fallback = useAntdForm();
  const instance = form ?? fallback[0];
  const methods = instance.__methods;

  /*
   * antd seeds the fields from `initialValues` ON MOUNT ONLY and documents
   * that later changes are ignored.
   *
   * Matching that exactly is load-bearing here, not pedantry: the call-sites
   * pass `initialValues={formDetails}` AND write `formDetails` from
   * `onValuesChange`. Re-applying on every change would reset the form to the
   * value it just reported — an infinite loop that clobbers typing mid-
   * keystroke. The ref makes it run once per mount, and `destroyOnClose`
   * remounts the modal so reopening still re-seeds.
   *
   * The seed goes UNDERNEATH anything already in the store, which is what
   * antd does (`setValues({}, initialValues, this.store)` — the store wins).
   * Modals that fetch before they render the form rely on it: Agentic Table
   * Settings shows a spinner while it loads, calls `setFieldsValue(fetched)`
   * from the response, and only then renders the `<Form>`. A plain
   * `reset(initialValues)` discarded that write, so every reopen showed the
   * defaults and the saved Lite LLM adapter came back blank.
   */
  const seeded = React.useRef(false);
  if (!seeded.current && initialValues) {
    seeded.current = true;
    methods.reset(mergeOverInitialValues(initialValues, methods.getValues()), {
      keepDefaultValues: false,
    });
  }

  /*
   * antd calls `onValuesChange(changedValues, allValues)` on every edit. This
   * was dropped, so handlers that mirror the form into component state never
   * ran: the state kept its initial value and Save posted an empty body while
   * looking like it did nothing. RHF's `watch` callback is the equivalent
   * subscription, and it reports the name of the field that changed.
   */
  React.useEffect(() => {
    if (!onValuesChange) {
      return undefined;
    }
    const subscription = methods.watch((allValues, { name: changedName }) => {
      if (!changedName) {
        return;
      }
      onValuesChange({ [changedName]: allValues[changedName] }, allValues);
    });
    return () => subscription.unsubscribe();
  }, [methods, onValuesChange]);

  return (
    <FormProvider {...methods}>
      <form
        ref={ref}
        className={cn(
          layout === "vertical" ? "space-y-4" : "space-y-3",
          className,
        )}
        onSubmit={
          onFinish
            ? methods.handleSubmit(onFinish, onFinishFailed)
            : (e) => e.preventDefault()
        }
        {...props}
      >
        {children}
      </form>
    </FormProvider>
  );
});

/**
 * antd accepts a NamePath: a string, or an array for nested fields —
 * `name={["email"]}`, `name={["tier1", "up_to"]}`. react-hook-form only takes
 * a string and calls `.split(".")` on it, so an array threw
 * `TypeError: s.split is not a function` from inside Controller and took the
 * whole route down with it (Invite Users was a blank error page).
 *
 * The array form is antd's dotted path, so joining reproduces it exactly.
 */
function toFieldName(name?: NamePath): string | undefined {
  return Array.isArray(name) ? name.join(".") : name;
}

type ItemTooltip = FormItemProps["tooltip"];

/** antd's `{ title, icon }` config form, as opposed to a bare node. */
function isTooltipConfig(
  tooltip: ItemTooltip,
): tooltip is { title?: React.ReactNode; icon?: React.ReactNode } {
  return (
    typeof tooltip === "object" &&
    tooltip !== null &&
    !React.isValidElement(tooltip) &&
    ("title" in tooltip || "icon" in tooltip)
  );
}

/**
 * antd's `<Form.Item tooltip>`: a marker after the label text that reveals the
 * hint on hover or focus.
 *
 * It was not declared, so every use fell into `...props` and landed on the
 * wrapper div — the icon never rendered and the object form (`tooltip={{
 * title, icon }}`) reached the DOM as a stray attribute. The Agentic and
 * Table Extraction settings modals lost all eleven of their field hints that
 * way, and so did the manual-review rule editors.
 *
 * Focusable by keyboard, unlike a bare icon: Radix only opens on hover and
 * focus, so a non-focusable trigger hides the hint from keyboard users.
 */
function renderLabelContent(label: React.ReactNode, tooltip: ItemTooltip) {
  const title = isTooltipConfig(tooltip) ? tooltip.title : tooltip;
  if (!title) {
    return label;
  }
  const icon = isTooltipConfig(tooltip) ? tooltip.icon : undefined;

  return (
    <>
      {label}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger
            type="button"
            // antd's marker is decorative next to a label that already names
            // the field; the accessible name says what activating it reveals.
            aria-label="More info"
            className="ant-form-item-tooltip ml-1 inline-flex cursor-help align-middle text-muted-foreground [&_svg]:size-3.5"
          >
            {icon ?? <CircleHelp />}
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">{title}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </>
  );
}

/**
 * antd `<Form.Item name label rules>`. Clones its single child and injects the
 * controlled `value`/`onChange`, which is how antd wires inputs too.
 */
function FormItem({
  name: rawName,
  label,
  rules,
  required,
  valuePropName = "value",
  initialValue,
  tooltip,
  /*
   * antd's server-error channel. The call-sites do NOT validate on the client
   * before submitting — they post, catch the 400, and feed the response into
   * `validateStatus="error"` + `help="<message>"` on the offending item.
   *
   * Both were falling into `...props` and landing on the wrapper div, so the
   * backend's message was never displayed (and React warned about unknown DOM
   * attributes). Submitting an invalid form therefore looked like the Save
   * button did nothing at all.
   */
  validateStatus,
  help,
  /*
   * antd's static hint, shown under the control whether or not the field is
   * errored — the token estimate under Chunk Size, the slug rules under an API
   * name. It was falling into `...props` and reaching the DOM as a stray
   * attribute on the wrapper div, so every one of these hints was invisible.
   */
  extra,
  className,
  children,
  ...props
}: FormItemProps) {
  const methods = useFormContext();
  const name = toFieldName(rawName);

  // Layout-only Form.Items (no `name`) just render their children.
  if (!name || !methods) {
    return (
      <div className={cn("space-y-2", className)} {...props}>
        {label ? <Label>{renderLabelContent(label, tooltip)}</Label> : null}
        {children}
        {help ? (
          <p
            className={cn(
              "text-sm",
              validateStatus === "error"
                ? "text-destructive"
                : "text-muted-foreground",
            )}
          >
            {help}
          </p>
        ) : null}
        {extra ? (
          <p className="ant-form-item-extra text-sm text-muted-foreground">
            {extra}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <Controller
      name={name}
      control={methods.control}
      // Only pass it through when the item actually declares one: RHF treats
      // an explicit `undefined` as "seed this field to undefined", which would
      // clobber a value already set via <Form initialValues> or setFieldsValue.
      {...(initialValue !== undefined ? { defaultValue: initialValue } : {})}
      rules={toRules(rules, label)}
      render={({ field, fieldState }) => {
        // The child is the control being wired. Narrowed to an element
        // because the injection below reads its existing id/onChange/onBlur
        // and hands them back so a child that sets its own keeps working.
        const child = React.Children.only(children) as React.ReactElement<{
          id?: string;
          className?: string;
          onChange?: (e: unknown) => void;
          onBlur?: (e: unknown) => void;
        }>;
        const injected = {
          // `<Label htmlFor={name}>` needs a matching id on the control, or
          // the label points at nothing — clicking it does not focus the
          // field and screen readers announce it unlabelled. antd wired this
          // for us; on the shim it has to be explicit. A child that sets its
          // own id keeps it.
          id: child.props.id ?? name,
          [valuePropName]:
            valuePropName === "checked"
              ? Boolean(field.value)
              : (field.value ?? ""),
          onChange: (e: unknown) => {
            // Works for both DOM events and value-first callbacks (Select).
            const target =
              e && typeof e === "object" && "target" in e
                ? (e as { target: HTMLInputElement }).target
                : null;
            const next = target
              ? valuePropName === "checked"
                ? target.checked
                : target.value
              : e;
            field.onChange(next);
            child.props.onChange?.(e);
          },
          onBlur: (e: unknown) => {
            field.onBlur();
            child.props.onBlur?.(e);
          },
        };

        // antd shows `help` in place of the rule message when it is set, and
        // `validateStatus` decides whether the control reads as errored.
        const hasError =
          validateStatus === "error" || Boolean(fieldState.error);
        const message = help ?? fieldState.error?.message;

        return (
          <div
            className={cn("ant-form-item space-y-2", className)}
            {...props}
            data-status={hasError ? "error" : undefined}
          >
            {label ? (
              <Label htmlFor={name}>
                {required ? <span className="text-destructive">* </span> : null}
                {renderLabelContent(label, tooltip)}
              </Label>
            ) : null}
            <div className="ant-form-item-control-input">
              {React.cloneElement(child, {
                ...injected,
                // Give the control itself the error ring, the way antd's
                // `validateStatus` does.
                ...(hasError
                  ? {
                      className: cn(
                        child.props.className,
                        "border-destructive focus-visible:ring-destructive",
                      ),
                    }
                  : {}),
              })}
            </div>
            {message ? (
              <p
                className={cn(
                  "text-sm",
                  hasError ? "text-destructive" : "text-muted-foreground",
                )}
              >
                {message}
              </p>
            ) : null}
            {/* After the error message, the way antd orders explain > extra. */}
            {extra ? (
              <p className="ant-form-item-extra text-sm text-muted-foreground">
                {extra}
              </p>
            ) : null}
          </div>
        );
      }}
    />
  );
}

/**
 * antd's `Form.useWatch(name, form)` — subscribe to one field's value and
 * re-render on change.
 *
 * antd accepts the form instance as the second argument or, inside a Form,
 * omits it and reads context. Both are supported: the explicit instance wins,
 * context is the fallback, matching antd's own resolution order.
 *
 * The `control` is passed explicitly rather than relying on react-hook-form's
 * own context lookup, because the instance from `useForm()` is frequently held
 * by a parent that renders the `<Form>` further down the tree — there is no
 * FormProvider above the caller in that arrangement.
 *
 * `defaultValue` covers the first render specifically. A watcher above the
 * `<Form>` runs BEFORE the child `Form.Item`'s Controller registers, so a
 * per-item `initialValue` is not yet readable and the field would come back
 * `undefined` for one render. Call-sites that distinguish `=== false` from
 * "not set" (an unchecked box vs an unloaded form) take the wrong branch on
 * that render, so pass the item's own seed here as well.
 */
function useAntdWatch(
  name: NamePath,
  form?: FormInstance,
  defaultValue?: unknown,
): unknown {
  const context = useFormContext();
  const control = form?.__methods?.control ?? context?.control;
  // A private throwaway control keeps the hook call unconditional when there is
  // no form to read (a watcher rendered outside any Form). `disabled` is not
  // enough on its own: useWatch dereferences `control._getWatch` while mounting,
  // before it consults the flag, so a null control throws.
  const fallback = useForm();
  const watched = useWatch({
    control: control ?? fallback.control,
    name: toFieldName(name) as string,
    disabled: !control,
    defaultValue,
  });
  return control ? watched : undefined;
}

/** Namespace object, so `<Form.Item>` type-checks and shim-completeness
 * still finds the statics by value. */
const Form = Object.assign(FormBase, {
  Item: FormItem,
  useForm: useAntdForm,
  useWatch: useAntdWatch,
  List: function FormList({ children }: { children?: React.ReactNode }) {
    return children;
  },
});

export { Form };

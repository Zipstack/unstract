import * as React from "react";
import {
  Controller,
  FormProvider,
  useForm,
  useFormContext,
} from "react-hook-form";

import { Label } from "@/components/ui/label";
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

/** Translate antd `rules` into RHF's validate/required options. */
function toRules(rules = [], label) {
  const out = {};
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
      out.validate = {
        ...(out.validate ?? {}),
        [`custom${Object.keys(out.validate ?? {}).length}`]: async (value) => {
          try {
            await rule.validator({}, value);
            return true;
          } catch (e) {
            return e?.message ?? rule.message ?? "Invalid value";
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
function useAntdForm() {
  const methods = useForm({ mode: "onSubmit", shouldUnregister: false });

  const instance = React.useMemo(
    () => ({
      __methods: methods,

      /** antd: set one or many fields. */
      setFieldsValue: (values = {}) => {
        for (const [k, v] of Object.entries(values)) {
          methods.setValue(k, v, { shouldDirty: false, shouldValidate: false });
        }
      },
      setFieldValue: (name, value) =>
        methods.setValue(name, value, { shouldDirty: true }),

      getFieldsValue: () => methods.getValues(),
      getFieldValue: (name) => methods.getValues(name),

      /**
       * antd resolves with the values and REJECTS when invalid — call-sites do
       * `await form.validateFields().catch(() => null)`, so the rejection has
       * to be preserved or invalid forms would submit.
       */
      validateFields: async () => {
        const ok = await methods.trigger();
        if (!ok) {
          const err = new Error("Validation failed");
          err.errorFields = Object.entries(methods.formState.errors).map(
            ([name, e]) => ({ name: [name], errors: [e?.message] }),
          );
          throw err;
        }
        return methods.getValues();
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

/** antd `<Form form layout onFinish>`. */
const Form = React.forwardRef(function Form(
  {
    form,
    layout = "horizontal",
    onFinish,
    onFinishFailed,
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
 * antd `<Form.Item name label rules>`. Clones its single child and injects the
 * controlled `value`/`onChange`, which is how antd wires inputs too.
 */
function FormItem({
  name,
  label,
  rules,
  required,
  valuePropName = "value",
  className,
  children,
  ...props
}) {
  const methods = useFormContext();

  // Layout-only Form.Items (no `name`) just render their children.
  if (!name || !methods) {
    return (
      <div className={cn("space-y-2", className)} {...props}>
        {label ? <Label>{label}</Label> : null}
        {children}
      </div>
    );
  }

  return (
    <Controller
      name={name}
      control={methods.control}
      rules={toRules(rules, label)}
      render={({ field, fieldState }) => {
        const child = React.Children.only(children);
        const injected = {
          [valuePropName]:
            valuePropName === "checked"
              ? Boolean(field.value)
              : (field.value ?? ""),
          onChange: (e) => {
            // Works for both DOM events and value-first callbacks (Select).
            const next =
              e && typeof e === "object" && "target" in e
                ? valuePropName === "checked"
                  ? e.target.checked
                  : e.target.value
                : e;
            field.onChange(next);
            child.props.onChange?.(e);
          },
          onBlur: (e) => {
            field.onBlur();
            child.props.onBlur?.(e);
          },
        };

        return (
          <div className={cn("space-y-2", className)} {...props}>
            {label ? (
              <Label htmlFor={name}>
                {required ? <span className="text-destructive">* </span> : null}
                {label}
              </Label>
            ) : null}
            {React.cloneElement(child, injected)}
            {fieldState.error ? (
              <p className="text-sm text-destructive">
                {fieldState.error.message}
              </p>
            ) : null}
          </div>
        );
      }}
    />
  );
}

Form.Item = FormItem;
Form.useForm = useAntdForm;
Form.List = function FormList({ children }) {
  return children;
};

export { Form };

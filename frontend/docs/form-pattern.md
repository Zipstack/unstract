# Form conversion pattern (P3-01)

The reviewed pattern that P3-02 applies to the remaining call-sites.

## The problem

antd's `Form` bundles validation, layout and state into one component, and this
codebase drives it **imperatively** through a form instance:

```jsx
const [form] = Form.useForm();
form.setFieldsValue({ name: group?.name });          // populate on edit
const values = await form.validateFields().catch(() => null);
if (!values) return;                                  // bail out when invalid
form.resetFields();
```

14 `useForm()` sites and 102 `Form.Item`s depend on that API. Rewriting each by
hand onto raw react-hook-form would mean 102 independent chances to change
submit or validation behaviour — and one wrong `.catch()` silently lets an
invalid form submit.

## The pattern: keep antd's API, swap the engine

`@/components/ui/antd-form` implements antd's `Form` surface on top of
react-hook-form. Call-sites convert **by import only**:

```diff
-import { Form, Input } from "antd";
+import { Form } from "@/components/ui/antd-form";
+import { Input } from "@/components/ui/input";
```

The JSX is untouched:

```jsx
<Form form={form} layout="vertical">
  <Form.Item
    label="Name"
    name="name"
    rules={[{ required: true, message: "Group name is required" }]}
  >
    <Input maxLength={255} />
  </Form.Item>
</Form>
```

## What the shim guarantees

| antd API | Behaviour preserved |
|---|---|
| `Form.useForm()` | Returns `[form]` with the imperative methods below |
| `form.setFieldsValue(obj)` | Populates fields — edit-mode modals depend on this |
| `form.getFieldsValue()` / `getFieldValue(n)` | Reads current values |
| `form.validateFields()` | **Rejects** when invalid, resolves with values when valid |
| `form.resetFields()` | Clears back to empty |
| `<Form.Item rules>` | `required`, `min`, `max`, `pattern`, and custom `validator` |
| `<Form.Item>` without `name` | Renders as plain layout |
| `onFinish` | Fires only when validation passes |

**The rejection semantics are the load-bearing part.** Call-sites are written as
`await form.validateFields().catch(() => null)` and bail on `null`. If
`validateFields` resolved on invalid input instead of rejecting, every one of
those guards would silently pass and submit bad data. Two unit tests pin this:
one asserts the rejection, one asserts `onFinish` does not fire while a required
field is empty.

## Rules translation

antd rule objects map onto RHF options:

| antd | RHF |
|---|---|
| `{ required: true, message }` | `required: message` |
| `{ max: n, message }` | `maxLength: { value: n, message }` |
| `{ min: n, message }` | `minLength: { value: n, message }` |
| `{ pattern: re, message }` | `pattern: { value: re, message }` |
| `{ validator: async fn }` | `validate: { customN: … }` — a thrown error's message becomes the inline message |

## Controlled-child injection

`Form.Item` clones its single child and injects `value`/`onChange`/`onBlur`,
which is how antd wires inputs too. `valuePropName="checked"` is honoured for
`Checkbox`/`Switch`. The child's own `onChange` still fires, so call-sites that
react to changes keep working.

## Reference conversion

`src/components/groups/GroupCreateEditModal.jsx` — a small modal exercising
`setFieldsValue` (edit mode), `validateFields().catch()` (submit guard),
`resetFields()` (cancel), and a `required` rule. Converted with an import change
only.

## When NOT to use the shim

New forms should use `react-hook-form` + `@/components/ui/form` directly. The
`antd-form` module exists to carry the existing 102 call-sites across without
behaviour drift, and should not grow new antd-only props.

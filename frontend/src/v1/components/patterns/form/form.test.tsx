import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Input } from "@v1/components/ui/form";
import { type ApiError, toApiError } from "@v1/services/errors";
import { AxiosError, AxiosHeaders, CanceledError } from "axios";
import { useState } from "react";
import { useFieldArray } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";
import {
  applyServerErrors,
  FormField,
  FormFooter,
  useAppForm,
  useLeaveGuard,
} from ".";

/** A failed request as the v1 client rejects it: axios's error through toApiError. */
function rejected(status: number, data: unknown): ApiError {
  const config = { headers: new AxiosHeaders() };
  const response = {
    status,
    statusText: "",
    data,
    headers: new AxiosHeaders(),
    config,
  };
  return toApiError(
    new AxiosError(`HTTP ${status}`, undefined, config, undefined, response),
  );
}

type FieldItem = Readonly<{ detail: string; attr?: string }>;
const invalid = (...errors: FieldItem[]): ApiError =>
  rejected(400, {
    type: "validation_error",
    errors: errors.map((e) => ({ code: "invalid", ...e })),
  });

const schema = z.object({
  name: z.string().min(1, "Enter a name"),
  url: z.string().url("Enter a URL"),
});
type Values = z.infer<typeof schema>;

let lastForm: ReturnType<typeof useAppForm<Values, Values>>;

function Sample({
  onSave = async () => undefined,
  defaults = { name: "a", url: "https://x.io" },
}: {
  /** Resolves with what a failed save throws, or undefined once saved. */
  onSave?: (v: Values) => Promise<unknown>;
  defaults?: Values;
}) {
  const form = useAppForm({ schema, defaultValues: defaults });
  lastForm = form;
  return (
    <form
      onSubmit={form.handleSubmit(async (values) => {
        const error = await onSave(values);
        if (error === undefined) {
          form.reset(values);
        } else {
          applyServerErrors(form, error);
        }
      })}
    >
      <FormField form={form} name="name" label="Name">
        {(field) => <Input {...field} />}
      </FormField>
      <FormField form={form} name="url" label="URL" helperText="Where it runs">
        {(field) => <Input {...field} />}
      </FormField>
      <FormFooter form={form} />
    </form>
  );
}

const saveButton = () =>
  screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement;
const discardButton = () =>
  screen.getByRole("button", { name: "Discard" }) as HTMLButtonElement;

const extraSchema = z.object({
  name: z.string().min(1),
  note: z.string().optional(),
  ownerId: z.string(),
});
type Extra = z.infer<typeof extraSchema>;

/** Holds ownerId without rendering it, and renders note with no default. */
function Extra({ onSave }: { onSave: (v: Extra) => Promise<unknown> }) {
  const form = useAppForm({
    schema: extraSchema,
    defaultValues: { name: "a", ownerId: "u1" },
  });
  return (
    <form
      onSubmit={form.handleSubmit(async (values) =>
        applyServerErrors(form, await onSave(values)),
      )}
    >
      <FormField form={form} name="name" label="Name">
        {(field) => <Input {...field} />}
      </FormField>
      <FormField form={form} name="note" label="Note">
        {(field) => <Input {...field} value={field.value ?? ""} />}
      </FormField>
      <FormFooter form={form} />
    </form>
  );
}

const refinedSchema = z
  .object({ name: z.string(), url: z.string() })
  .refine((v) => v.name !== v.url, "Name and URL must differ");

/** A whole-form refine with no path: its error belongs to no field. */
function Refined() {
  const form = useAppForm({
    schema: refinedSchema,
    defaultValues: { name: "", url: "b" },
  });
  return (
    <form onSubmit={form.handleSubmit(() => undefined)}>
      <FormField form={form} name="name" label="Name">
        {(field) => <Input {...field} />}
      </FormField>
      <FormFooter form={form} />
    </form>
  );
}

describe("useAppForm and FormField", () => {
  it("validates a field on blur and wires its error to the control", async () => {
    render(<Sample />);
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    await act(async () => undefined);
    expect(screen.queryByText("Enter a name")).toBeNull();
    fireEvent.blur(name);
    await screen.findByText("Enter a name");
    expect(name.getAttribute("aria-invalid")).toBe("true");
    expect(name.getAttribute("aria-describedby")).toContain(
      screen.getByText("Enter a name").id,
    );
  });

  it("focuses the first invalid field on submit and does not save", async () => {
    const onSave = vi.fn();
    render(<Sample onSave={onSave} defaults={{ name: "", url: "" }} />);
    // Name was never blurred, so no error shows until the submit.
    await userEvent.type(screen.getByLabelText("URL"), "x");
    const form = screen.getByLabelText("URL").closest("form");
    fireEvent.submit(form as HTMLFormElement);
    await screen.findByText("Enter a name");
    screen.getByText("Enter a URL");
    expect(document.activeElement).toBe(screen.getByLabelText("Name"));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("moves focus to the first field a server error names", async () => {
    const onSave = async () =>
      invalid(
        { detail: "That URL is taken", attr: "url" },
        { detail: "That name is taken", attr: "name" },
      );
    render(<Sample onSave={onSave} />);
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("That URL is taken");
    expect(document.activeElement).toBe(screen.getByLabelText("URL"));
  });

  it("clears a blur error as soon as the field is fixed", async () => {
    render(<Sample />);
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    fireEvent.blur(name);
    await screen.findByText("Cannot save");
    await userEvent.type(name, "fixed");
    await screen.findByText("1 unsaved change");
    expect(screen.queryByText("Enter a name")).toBeNull();
    expect(saveButton().disabled).toBe(false);
  });
});

describe("applyServerErrors", () => {
  it("puts a known attr on its field and the rest at form level", async () => {
    const onSave = async () =>
      invalid(
        { detail: "Name is taken", attr: "name" },
        { detail: "Quota reached", attr: "non_field_errors" },
        { detail: "Bad owner", attr: "owner" },
      );
    render(<Sample onSave={onSave} />);
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("Name is taken");
    expect(screen.getByLabelText("Name").getAttribute("aria-invalid")).toBe(
      "true",
    );
    // An attr with no field keeps its name, so its detail is not read alone.
    expect(
      screen.getByText("Quota reached owner: Bad owner").getAttribute("role"),
    ).toBe("alert");
  });

  it("reads axios's error as thrown, before anything normalises it", async () => {
    const config = { headers: new AxiosHeaders() };
    const raw = new AxiosError("HTTP 400", undefined, config, undefined, {
      status: 400,
      statusText: "",
      data: {
        type: "validation_error",
        errors: [{ code: "x", detail: "Name is taken", attr: "name" }],
      },
      headers: new AxiosHeaders(),
      config,
    });
    render(<Sample onSave={async () => raw} />);
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("Name is taken");
    expect(screen.getByLabelText("Name").getAttribute("aria-invalid")).toBe(
      "true",
    );
  });

  it("maps a dotted attr onto a nested path", () => {
    const setError = vi.fn();
    const form = {
      control: { _fields: { rows: [{ key: { _f: { mount: true } } }] } },
      setError,
    } as unknown as Parameters<typeof applyServerErrors>[0];
    applyServerErrors(form, invalid({ detail: "Bad key", attr: "rows.0.key" }));
    expect(setError).toHaveBeenCalledWith(
      "rows.0.key",
      { type: "server", message: "Bad key" },
      { shouldFocus: true },
    );
  });

  it("puts a non-validation failure at form level", () => {
    const setError = vi.fn();
    const form = {
      control: { _fields: { name: { _f: { mount: true } } } },
      setError,
    } as unknown as Parameters<typeof applyServerErrors>[0];
    applyServerErrors(
      form,
      rejected(500, {
        type: "server_error",
        errors: [{ code: "error", detail: "Something broke", attr: "name" }],
      }),
    );
    expect(setError).toHaveBeenCalledTimes(1);
    expect(setError).toHaveBeenCalledWith("root.server", {
      type: "server",
      message: "Something broke",
    });
  });

  it("sets nothing for a cancelled request", () => {
    const setError = vi.fn();
    const form = {
      control: { _fields: {} },
      setError,
    } as unknown as Parameters<typeof applyServerErrors>[0];
    applyServerErrors(form, new CanceledError());
    expect(setError).not.toHaveBeenCalled();
  });

  it("shows every error the server sent for one field", async () => {
    render(
      <Sample
        onSave={async () =>
          invalid(
            { detail: "Too short.", attr: "name" },
            { detail: "Taken.", attr: "name" },
          )
        }
      />,
    );
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    expect(await screen.findByText("Too short. Taken.")).toBeInTheDocument();
  });

  it("puts a field's error under it even when its value is undefined", async () => {
    render(
      <Extra
        onSave={async () => invalid({ detail: "Bad note", attr: "note" })}
      />,
    );
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("Bad note");
    expect(screen.getByLabelText("Note").getAttribute("aria-invalid")).toBe(
      "true",
    );
  });

  it("shows an error for a value no field renders at form level and keeps Save enabled", async () => {
    render(
      <Extra
        onSave={async () => invalid({ detail: "Owner gone", attr: "ownerId" })}
      />,
    );
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("ownerId: Owner gone");
    screen.getByText("1 unsaved change");
    expect(saveButton().disabled).toBe(false);
  });

  it("shows a form-level-only error without blocking Save", async () => {
    render(
      <Sample
        onSave={async () =>
          invalid({ detail: "Quota reached", attr: "non_field_errors" })
        }
      />,
    );
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("Quota reached");
    screen.getByText("1 unsaved change");
    expect(saveButton().disabled).toBe(false);
  });

  it.each([
    [
      "a 400 with a detail",
      rejected(400, { detail: "Request failed" }),
      "Request failed",
    ],
    [
      "a typed provider error",
      rejected(502, { type: "sdk_error", error: "Adapter down" }),
      "Adapter down",
    ],
    [
      "a validation error with no items",
      rejected(400, { type: "validation_error", errors: [] }),
      "Some fields need attention.",
    ],
    [
      "no response",
      toApiError(new AxiosError("Network Error")),
      "Can't reach the server. Check your connection and try again.",
    ],
    ["a plain Error", new Error("boom"), "Something went wrong."],
  ])("always shows something for %s", async (_, error, message) => {
    render(<Sample onSave={async () => error} />);
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    expect(await screen.findByText(message)).toBeInTheDocument();
  });
});

describe("cross-field rules", () => {
  const passwords = z
    .object({ name: z.string(), password: z.string(), confirm: z.string() })
    .refine((v) => v.password === v.confirm, {
      message: "Passwords do not match",
      path: ["confirm"],
    });

  function PasswordForm({ onSave }: { onSave: () => Promise<unknown> }) {
    const form = useAppForm({
      schema: passwords,
      defaultValues: { name: "a", password: "", confirm: "" },
    });
    return (
      <form
        onSubmit={form.handleSubmit(async () =>
          applyServerErrors(form, await onSave()),
        )}
      >
        {(["name", "password", "confirm"] as const).map((key) => (
          <FormField key={key} form={form} name={key} label={key}>
            {(field) => <Input {...field} />}
          </FormField>
        ))}
        <FormFooter form={form} />
      </form>
    );
  }

  it("re-checks a field whose error depends on the one that changed", async () => {
    render(
      <PasswordForm
        onSave={async () => invalid({ detail: "Name taken", attr: "name" })}
      />,
    );
    await userEvent.type(screen.getByLabelText("password"), "abc");
    await userEvent.type(screen.getByLabelText("confirm"), "ab");
    await userEvent.click(saveButton());
    await screen.findByText("Passwords do not match");
    expect(saveButton().disabled).toBe(true);
    // Fix the password, not the field that holds the error.
    await userEvent.clear(screen.getByLabelText("password"));
    await userEvent.type(screen.getByLabelText("password"), "ab");
    await vi.waitFor(() =>
      expect(screen.queryByText("Passwords do not match")).toBeNull(),
    );
    expect(saveButton().disabled).toBe(false);
    // The re-check leaves a server error alone: it clears on its own field's
    // change or the next submit.
    await userEvent.click(saveButton());
    await screen.findByText("Name taken");
    await userEvent.type(screen.getByLabelText("confirm"), "x");
    await screen.findByText("Passwords do not match");
    await userEvent.type(screen.getByLabelText("password"), "x");
    await vi.waitFor(() =>
      expect(screen.queryByText("Passwords do not match")).toBeNull(),
    );
    screen.getByText("Name taken");
  });
});

describe("hidden and nested fields", () => {
  const nested = z.object({
    name: z.string().min(1),
    rows: z.array(z.object({ key: z.string().min(1, "Enter a key") })),
  });
  type Nested = z.infer<typeof nested>;

  /** URL can be hidden; rows.0.key is a nested field. */
  function Toggle({ onSave }: { onSave?: (v: Nested) => Promise<unknown> }) {
    const [shown, setShown] = useState(true);
    const form = useAppForm({
      schema: nested,
      defaultValues: { name: "a", rows: [{ key: "k" }] },
    });
    return (
      <form
        onSubmit={form.handleSubmit(async (values) => {
          if (onSave) {
            applyServerErrors(form, await onSave(values));
          }
        })}
      >
        <FormField form={form} name="name" label="Name">
          {(field) => <Input {...field} />}
        </FormField>
        {shown ? (
          <FormField form={form} name="rows.0.key" label="Key">
            {(field) => <Input {...field} />}
          </FormField>
        ) : null}
        <button type="button" onClick={() => setShown(false)}>
          Hide
        </button>
        <FormFooter form={form} />
      </form>
    );
  }

  it("blocks Save on a nested field's error and shows it under the field", async () => {
    render(<Toggle />);
    const key = screen.getByLabelText("Key");
    await userEvent.clear(key);
    fireEvent.blur(key);
    await screen.findByText("Cannot save");
    expect(screen.getAllByText("Enter a key")).toHaveLength(1);
    expect(saveButton().disabled).toBe(true);
  });

  it("frees Save when a field holding an error is hidden", async () => {
    render(<Toggle />);
    const key = screen.getByLabelText("Key");
    await userEvent.clear(key);
    fireEvent.blur(key);
    await screen.findByText("Cannot save");
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    await screen.findByText("1 unsaved change");
    expect(saveButton().disabled).toBe(false);
  });

  it("sends a server error for a hidden field to the footer", async () => {
    render(
      <Toggle
        onSave={async () =>
          invalid({ detail: "Key taken", attr: "rows.0.key" })
        }
      />,
    );
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    await userEvent.click(saveButton());
    await screen.findByText("rows.0.key: Key taken");
    expect(saveButton().disabled).toBe(false);
  });
});

describe("field arrays and locked fields", () => {
  const listSchema = z.object({
    rows: z.array(z.object({ key: z.string().min(1, "Enter a key") })),
  });
  type List = z.infer<typeof listSchema>;

  /** Rows keyed by field id, each with a Remove button. */
  function Rows() {
    const form = useAppForm({
      schema: listSchema,
      defaultValues: { rows: [{ key: "a" }, { key: "" }, { key: "" }] },
    });
    const { fields, remove } = useFieldArray<List>({
      control: form.control,
      name: "rows",
    });
    return (
      <form onSubmit={form.handleSubmit(() => undefined)}>
        {fields.map((row, index) => (
          <div key={row.id}>
            <FormField
              form={form}
              name={`rows.${index}.key`}
              label={`Key ${index}`}
            >
              {(field) => <Input {...field} />}
            </FormField>
            <button type="button" onClick={() => remove(index)}>
              Remove {index}
            </button>
          </div>
        ))}
        <FormFooter form={form} />
      </form>
    );
  }

  it("keeps the other rows' errors when a row is removed", async () => {
    render(<Rows />);
    await userEvent.type(screen.getByLabelText("Key 0"), "b");
    await userEvent.click(saveButton());
    await vi.waitFor(() =>
      expect(screen.getAllByText("Enter a key")).toHaveLength(2),
    );
    await userEvent.click(screen.getByRole("button", { name: "Remove 0" }));
    await act(async () => undefined);
    expect(screen.getAllByText("Enter a key")).toHaveLength(2);
    expect(saveButton().disabled).toBe(true);
  });

  it("keeps the other rows' blur errors when a row is removed before any submit", async () => {
    render(<Rows />);
    fireEvent.blur(screen.getByLabelText("Key 1"));
    fireEvent.blur(screen.getByLabelText("Key 2"));
    await vi.waitFor(() =>
      expect(screen.getAllByText("Enter a key")).toHaveLength(2),
    );
    await userEvent.click(screen.getByRole("button", { name: "Remove 0" }));
    await act(async () => undefined);
    expect(screen.getAllByText("Enter a key")).toHaveLength(2);
  });

  const lockedSchema = z.object({ name: z.string(), slug: z.string() });

  /** Slug is shown but cannot be edited. */
  function Locked({ onSave }: { onSave: () => Promise<unknown> }) {
    const form = useAppForm({
      schema: lockedSchema,
      defaultValues: { name: "a", slug: "s" },
    });
    return (
      <form
        onSubmit={form.handleSubmit(async () =>
          applyServerErrors(form, await onSave()),
        )}
      >
        <FormField form={form} name="name" label="Name">
          {(field) => <Input {...field} />}
        </FormField>
        <FormField form={form} name="slug" label="Slug">
          {(field) => <Input {...field} disabled />}
        </FormField>
        <FormFooter form={form} />
      </form>
    );
  }

  it("does not lock Save on a server error the user cannot clear", async () => {
    render(
      <Locked
        onSave={async () => invalid({ detail: "Slug taken", attr: "slug" })}
      />,
    );
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("Slug taken");
    await userEvent.type(screen.getByLabelText("Name"), "c");
    expect(await screen.findByText("1 unsaved change")).toBeInTheDocument();
    expect(saveButton().disabled).toBe(false);
  });
});

describe("FormFooter", () => {
  it("shows No changes with Save disabled on a clean form", () => {
    render(<Sample />);
    screen.getByText("No changes");
    expect(saveButton().disabled).toBe(true);
    expect(discardButton().disabled).toBe(true);
  });

  it("counts dirty fields, and Discard restores the saved values", async () => {
    render(<Sample />);
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await screen.findByText("1 unsaved change");
    await userEvent.type(screen.getByLabelText("URL"), "/p");
    await screen.findByText("2 unsaved changes");
    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    await screen.findByText("No changes");
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("a");
  });

  it("drops schema errors on Discard after a failed submit", async () => {
    render(<Sample defaults={{ name: "", url: "https://x.io" }} />);
    await userEvent.type(screen.getByLabelText("URL"), "/p");
    fireEvent.submit(
      screen.getByLabelText("URL").closest("form") as HTMLFormElement,
    );
    await screen.findByText("Enter a name");
    await userEvent.click(discardButton());
    await screen.findByText("No changes");
    await act(async () => undefined);
    expect(screen.queryByText("Enter a name")).toBeNull();
    expect(screen.getByLabelText("Name").getAttribute("aria-invalid")).not.toBe(
      "true",
    );
  });

  it("gives Save and Discard stable test ids", () => {
    render(<Sample />);
    expect(screen.getByTestId("form-footer-save")).toBe(saveButton());
    expect(screen.getByTestId("form-footer-discard")).toBe(discardButton());
  });

  it("shows Cannot save while a field error stands", async () => {
    render(<Sample />);
    await userEvent.clear(screen.getByLabelText("Name"));
    fireEvent.blur(screen.getByLabelText("Name"));
    await screen.findByText("Cannot save");
    expect(saveButton().disabled).toBe(true);
  });

  it("shows No changes on a clean form even with a field error", async () => {
    render(<Sample defaults={{ name: "", url: "https://x.io" }} />);
    fireEvent.blur(screen.getByLabelText("Name"));
    expect(await screen.findByText("Enter a name")).toBeInTheDocument();
    expect(screen.getByText("No changes")).toBeInTheDocument();
  });

  it("shows a schema error that no field owns, without blocking Save", async () => {
    render(<Refined />);
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("Name and URL must differ");
    expect(saveButton().disabled).toBe(false);
  });

  it("hides a form-level error once the change is reverted", async () => {
    render(
      <Sample
        onSave={async () =>
          rejected(409, {
            type: "client_error",
            errors: [{ code: "x", detail: "Locked", attr: null }],
          })
        }
      />,
    );
    const name = screen.getByLabelText("Name");
    await userEvent.type(name, "b");
    await userEvent.click(saveButton());
    await screen.findByText("Locked");
    await userEvent.type(name, "{backspace}");
    await screen.findByText("No changes");
    expect(screen.queryByText("Locked")).toBeNull();
  });

  it("shows Saving while the save runs, then No changes", async () => {
    let finish: () => void = () => undefined;
    const onSave = () =>
      new Promise<undefined>((resolve) => {
        finish = () => resolve(undefined);
      });
    render(<Sample onSave={onSave} />);
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Saving");
    expect(saveButton().disabled).toBe(true);
    expect(discardButton().disabled).toBe(true);
    await act(async () => finish());
    await screen.findByText("No changes");
    expect(lastForm.getValues("name")).toBe("ab");
  });
});

describe("useLeaveGuard", () => {
  function Guarded({
    dirty,
    confirm,
    onLeave,
  }: {
    dirty: boolean;
    confirm: () => Promise<boolean>;
    onLeave: (ok: boolean) => void;
  }) {
    const confirmLeave = useLeaveGuard(dirty, confirm);
    return (
      <button type="button" onClick={async () => onLeave(await confirmLeave())}>
        Close
      </button>
    );
  }

  it("leaves a clean form without asking", async () => {
    const confirm = vi.fn(async () => false);
    const onLeave = vi.fn();
    render(<Guarded dirty={false} confirm={confirm} onLeave={onLeave} />);
    await userEvent.click(screen.getByRole("button"));
    expect(confirm).not.toHaveBeenCalled();
    expect(onLeave).toHaveBeenCalledWith(true);
  });

  it.each([
    true,
    false,
  ])("asks on a dirty form and returns the answer %s", async (answer) => {
    const onLeave = vi.fn();
    render(<Guarded dirty confirm={async () => answer} onLeave={onLeave} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onLeave).toHaveBeenCalledWith(answer);
  });

  it("asks once the form turns dirty", async () => {
    const confirm = vi.fn(async () => false);
    const onLeave = vi.fn();
    const { rerender } = render(
      <Guarded dirty={false} confirm={confirm} onLeave={onLeave} />,
    );
    rerender(<Guarded dirty confirm={confirm} onLeave={onLeave} />);
    await userEvent.click(screen.getByRole("button"));
    expect(confirm).toHaveBeenCalledOnce();
    expect(onLeave).toHaveBeenCalledWith(false);
  });

  it("asks the browser before a tab close only while dirty", () => {
    const confirm = async () => true;
    const { rerender } = render(
      <Guarded dirty confirm={confirm} onLeave={() => undefined} />,
    );
    const dirtyClose = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyClose);
    expect(dirtyClose.defaultPrevented).toBe(true);

    rerender(
      <Guarded dirty={false} confirm={confirm} onLeave={() => undefined} />,
    );
    const cleanClose = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(cleanClose);
    expect(cleanClose.defaultPrevented).toBe(false);
  });
});

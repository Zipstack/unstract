import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Input } from "@v1/components/ui/form";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";
import {
  applyServerErrors,
  FormField,
  FormFooter,
  type ServerErrorBody,
  useAppForm,
  useLeaveGuard,
} from ".";

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
  onSave?: (v: Values) => Promise<ServerErrorBody | undefined>;
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
function Extra({ onSave }: { onSave: (v: Extra) => Promise<ServerErrorBody> }) {
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
    const onSave = async () => ({
      type: "validation_error" as const,
      errors: [
        { code: "unique", detail: "Name is taken", attr: "name" },
        { code: "invalid", detail: "Quota reached", attr: "non_field_errors" },
        { code: "invalid", detail: "Bad owner", attr: "owner" },
      ],
    });
    render(<Sample onSave={onSave} />);
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Name is taken");
    expect(
      screen.getByText("Quota reached Bad owner").getAttribute("role"),
    ).toBe("alert");
  });

  it("maps a dotted attr onto a nested path", () => {
    const setError = vi.fn();
    const form = {
      control: { _fields: { rows: [{ key: { _f: { mount: true } } }] } },
      setError,
    } as unknown as Parameters<typeof applyServerErrors>[0];
    applyServerErrors(form, {
      type: "validation_error",
      errors: [{ code: "x", detail: "Bad key", attr: "rows.0.key" }],
    });
    expect(setError).toHaveBeenCalledWith("rows.0.key", {
      type: "server",
      message: "Bad key",
    });
  });

  it("puts every error of a non-validation response at form level", () => {
    const setError = vi.fn();
    const form = {
      control: { _fields: { name: { _f: { mount: true } } } },
      setError,
    } as unknown as Parameters<typeof applyServerErrors>[0];
    applyServerErrors(form, {
      type: "server_error",
      errors: [{ code: "error", detail: "Something broke", attr: "name" }],
    });
    expect(setError).toHaveBeenCalledWith("root.server", {
      type: "server",
      message: "Something broke",
    });
  });

  it("shows every error the server sent for one field", async () => {
    render(
      <Sample
        onSave={async () => ({
          type: "validation_error",
          errors: [
            { code: "a", detail: "Too short.", attr: "name" },
            { code: "b", detail: "Taken.", attr: "name" },
          ],
        })}
      />,
    );
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("Too short. Taken.");
  });

  it("puts a field's error under it even when its value is undefined", async () => {
    render(
      <Extra
        onSave={async () => ({
          type: "validation_error",
          errors: [{ code: "x", detail: "Bad note", attr: "note" }],
        })}
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
        onSave={async () => ({
          type: "validation_error",
          errors: [{ code: "x", detail: "Owner gone", attr: "ownerId" }],
        })}
      />,
    );
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("Owner gone");
    screen.getByText("1 unsaved change");
    expect(saveButton().disabled).toBe(false);
  });

  it("shows a form-level-only error without blocking Save", async () => {
    render(
      <Sample
        onSave={async () => ({
          type: "validation_error",
          errors: [
            { code: "x", detail: "Quota reached", attr: "non_field_errors" },
          ],
        })}
      />,
    );
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText("Quota reached");
    screen.getByText("1 unsaved change");
    expect(saveButton().disabled).toBe(false);
  });

  it.each([
    [{ detail: "Request failed" }, "Request failed"],
    [{ type: "sdk_error", error: "Adapter down" }, "Adapter down"],
    [{ type: "validation_error", errors: [] }, "Could not save. Try again."],
    [
      {
        type: "validation_error",
        errors: [{ code: "x", detail: "", attr: null }],
      },
      "Could not save. Try again.",
    ],
    [null, "Could not save. Try again."],
  ])("always shows something for the body %j", async (body, message) => {
    render(<Sample onSave={async () => body as never} />);
    await userEvent.type(screen.getByLabelText("Name"), "b");
    await userEvent.click(saveButton());
    await screen.findByText(message);
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
    await screen.findByText("Enter a name");
    screen.getByText("No changes");
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
        onSave={async () => ({
          type: "client_error",
          errors: [{ code: "x", detail: "Locked", attr: null }],
        })}
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

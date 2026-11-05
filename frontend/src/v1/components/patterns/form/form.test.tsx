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
        if (error) {
          applyServerErrors(form, error);
        } else {
          form.reset(values);
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

describe("useAppForm and FormField", () => {
  it("validates a field on blur and wires its error to the control", async () => {
    render(<Sample />);
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
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
      getValues: () => ({ rows: [{ key: "k" }] }),
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
      getValues: () => ({ name: "" }),
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
});

describe("FormFooter", () => {
  it("shows No changes with Save disabled on a clean form", () => {
    render(<Sample />);
    screen.getByText("No changes");
    expect(
      (
        screen.getByRole("button", {
          name: "Save changes",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
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
    expect(
      (
        screen.getByRole("button", {
          name: "Save changes",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
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

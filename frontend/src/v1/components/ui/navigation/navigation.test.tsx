import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "./Accordion";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "./Breadcrumb";
import { Checklist } from "./Checklist";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "./Collapsible";
import { CHECKLIST_STEPS, STEPPER_STEPS } from "./navigation.gallery";
import { Pagination, pageCount, rangeText } from "./Pagination";
import { Stepper } from "./Stepper";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./Tabs";

function renderTabs(onValueChange = vi.fn(), variant?: "bar" | "segmented") {
  render(
    <Tabs variant={variant} defaultValue="a" onValueChange={onValueChange}>
      <TabsList aria-label="Views">
        <TabsTrigger value="a">Alpha</TabsTrigger>
        <TabsTrigger value="b" disabled>
          Beta
        </TabsTrigger>
        <TabsTrigger value="c">Gamma</TabsTrigger>
      </TabsList>
      <TabsContent value="a">Alpha panel</TabsContent>
      <TabsContent value="b">Beta panel</TabsContent>
      <TabsContent value="c">Gamma panel</TabsContent>
    </Tabs>,
  );
  return onValueChange;
}

describe("Tabs", () => {
  it.each([
    "bar",
    "segmented",
  ] as const)("%s: exposes the selected tab and its panel", (variant) => {
    renderTabs(vi.fn(), variant);
    const list = screen.getByRole("tablist", { name: "Views" });
    const alpha = within(list).getByRole("tab", { name: "Alpha" });
    expect(alpha.getAttribute("aria-selected")).toBe("true");
    expect(
      within(list)
        .getByRole("tab", { name: "Gamma" })
        .getAttribute("aria-selected"),
    ).toBe("false");
    expect(screen.getByRole("tabpanel").textContent).toBe("Alpha panel");
    expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe(
      alpha.id,
    );
  });

  it("moves with the arrow keys, skips a disabled tab and activates on focus", async () => {
    const user = userEvent.setup();
    const onValueChange = renderTabs();
    await user.tab();
    expect(document.activeElement?.textContent).toBe("Alpha");
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement?.textContent).toBe("Gamma");
    expect(onValueChange).toHaveBeenLastCalledWith("c");
    expect(screen.getByRole("tabpanel").textContent).toBe("Gamma panel");
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement?.textContent).toBe("Alpha");
    await user.keyboard("{End}");
    expect(document.activeElement?.textContent).toBe("Gamma");
    await user.keyboard("{Home}");
    expect(document.activeElement?.textContent).toBe("Alpha");
    expect(onValueChange).toHaveBeenLastCalledWith("a");
  });

  it("selects on click and leaves the tab row with Tab", async () => {
    const user = userEvent.setup();
    renderTabs();
    await user.click(screen.getByRole("tab", { name: "Gamma" }));
    expect(
      screen.getByRole("tab", { name: "Gamma" }).getAttribute("aria-selected"),
    ).toBe("true");
    await user.tab();
    expect(document.activeElement?.getAttribute("role")).toBe("tabpanel");
  });

  it("marks the variant for styling", () => {
    renderTabs(vi.fn(), "segmented");
    expect(
      document.querySelector("[data-slot=tabs]")?.getAttribute("data-variant"),
    ).toBe("segmented");
  });
});

describe("Breadcrumb", () => {
  it("is a named landmark with the current page marked", () => {
    render(
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/wf">Workflows</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Invoices</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>,
    );
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(
      within(nav).getByRole("link", { name: "Workflows" }).getAttribute("href"),
    ).toBe("/wf");
    expect(within(nav).getByText("Invoices").getAttribute("aria-current")).toBe(
      "page",
    );
    // The separator is not a list item to assistive technology.
    expect(within(nav).getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders a router link through asChild", () => {
    render(
      <BreadcrumbLink asChild>
        <button type="button">Home</button>
      </BreadcrumbLink>,
    );
    const home = screen.getByRole("button", { name: "Home" });
    expect(home.getAttribute("data-slot")).toBe("breadcrumb-link");
  });
});

describe("Accordion", () => {
  it("opens one section at a time and moves between headers by keyboard", async () => {
    const user = userEvent.setup();
    render(
      <Accordion type="single" collapsible>
        <AccordionItem value="one">
          <AccordionTrigger>One</AccordionTrigger>
          <AccordionContent>First</AccordionContent>
        </AccordionItem>
        <AccordionItem value="two">
          <AccordionTrigger>Two</AccordionTrigger>
          <AccordionContent>Second</AccordionContent>
        </AccordionItem>
      </Accordion>,
    );
    const one = screen.getByRole("button", { name: "One" });
    const two = screen.getByRole("button", { name: "Two" });
    expect(one.getAttribute("aria-expanded")).toBe("false");
    await user.click(one);
    expect(one.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("First")).toBeTruthy();
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(two);
    await user.keyboard("{Enter}");
    expect(two.getAttribute("aria-expanded")).toBe("true");
    expect(one.getAttribute("aria-expanded")).toBe("false");
    await user.keyboard("{Enter}");
    expect(two.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("Collapsible", () => {
  it("shows and hides its region and reports the state", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <Collapsible onOpenChange={onOpenChange}>
        <CollapsibleTrigger>Logs</CollapsibleTrigger>
        <CollapsibleContent>Run started</CollapsibleContent>
      </Collapsible>,
    );
    const trigger = screen.getByRole("button", { name: "Logs" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Run started")).toBeNull();
    await user.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(onOpenChange).toHaveBeenLastCalledWith(true);
    const region = screen.getByText("Run started");
    expect(trigger.getAttribute("aria-controls")).toBe(region.id);
  });

  it("wires its state onto a custom trigger with asChild", async () => {
    const user = userEvent.setup();
    render(
      <Collapsible>
        <CollapsibleTrigger asChild>
          <button type="button">Mine</button>
        </CollapsibleTrigger>
        <CollapsibleContent>Body</CollapsibleContent>
      </Collapsible>,
    );
    const trigger = screen.getByRole("button", { name: "Mine" });
    await user.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(trigger.querySelector("svg")).toBeNull();
  });
});

describe("Checklist", () => {
  it("names each step with its state as text", () => {
    render(<Checklist aria-label="Setup" steps={CHECKLIST_STEPS} />);
    const items = within(
      screen.getByRole("list", { name: "Setup" }),
    ).getAllByRole("listitem");
    expect(items.map((item) => item.getAttribute("data-state"))).toEqual([
      "done",
      "in-progress",
      "not-started",
      "failed",
    ]);
    expect(items[0]?.textContent).toContain("Source connector, done");
    expect(items[1]?.textContent).toContain(
      "Destination connector, in progress",
    );
    expect(items[2]?.textContent).toContain(
      "Prompt Studio project, not started",
    );
    expect(items[3]?.textContent).toContain("Deploy workflow, failed");
    expect(items[0]?.textContent).toContain("s3_staging · /invoice");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("opens a step on click or keyboard and marks the current one", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <Checklist
        aria-label="Setup"
        steps={[
          ...CHECKLIST_STEPS.slice(0, 3),
          {
            id: "locked",
            label: "Locked",
            state: "not-started",
            disabled: true,
          },
        ]}
        currentId="destination"
        onSelect={onSelect}
      />,
    );
    const destination = screen.getByRole("button", {
      name: /Destination connector\s?, in progress/,
    });
    expect(destination.getAttribute("aria-current")).toBe("step");
    expect(
      screen
        .getByRole("button", { name: /Source connector/ })
        .getAttribute("aria-current"),
    ).toBeNull();
    await user.click(screen.getByRole("button", { name: /Source connector/ }));
    expect(onSelect).toHaveBeenLastCalledWith("source");
    screen.getByRole("button", { name: /Prompt Studio project/ }).focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith("project");
    await user.click(screen.getByRole("button", { name: /Locked/ }));
    expect(onSelect).toHaveBeenCalledTimes(2);
  });
});

describe("Stepper", () => {
  it("marks the step in progress as current and reads every state", () => {
    render(<Stepper aria-label="Stages" steps={STEPPER_STEPS} />);
    const items = within(
      screen.getByRole("list", { name: "Stages" }),
    ).getAllByRole("listitem");
    expect(items.map((item) => item.getAttribute("aria-current"))).toEqual([
      null,
      "step",
      null,
      null,
    ]);
    expect(items[3]?.textContent).toContain("Export, failed");
    expect(items[1]?.textContent).toContain("4 of 12");
    // A rule joins each pair of steps, primary after a done step.
    const rules = document.querySelectorAll("[data-slot=stepper-rule]");
    expect(rules).toHaveLength(3);
    expect(rules[0]?.className).toContain("ui:bg-primary");
    expect(rules[1]?.className).toContain("ui:bg-border");
  });
});

describe("Pagination", () => {
  it("computes pages and range text", () => {
    expect(pageCount(42, 10)).toBe(5);
    expect(pageCount(40, 10)).toBe(4);
    expect(pageCount(0, 10)).toBe(1);
    expect(pageCount(5, 0)).toBe(1);
    expect(rangeText(1, 10, 42)).toBe("Showing 1 to 10 of 42 entries");
    expect(rangeText(5, 10, 42)).toBe("Showing 41 to 42 of 42 entries");
    expect(rangeText(1, 10, 1)).toBe("Showing 1 to 1 of 1 entry");
    expect(rangeText(1, 10, 0)).toBe("No entries");
  });

  it("disables Previous on the first page and Next on the last", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    const { rerender } = render(
      <Pagination
        page={1}
        pageSize={10}
        total={42}
        onPageChange={onPageChange}
      />,
    );
    const nav = screen.getByRole("navigation", { name: "Pagination" });
    const previous = within(nav).getByRole("button", { name: "Previous" });
    const next = within(nav).getByRole("button", { name: "Next" });
    expect(previous.hasAttribute("disabled")).toBe(true);
    await user.click(next);
    expect(onPageChange).toHaveBeenLastCalledWith(2);
    rerender(
      <Pagination
        page={5}
        pageSize={10}
        total={42}
        onPageChange={onPageChange}
      />,
    );
    expect(next.hasAttribute("disabled")).toBe(true);
    await user.click(previous);
    expect(onPageChange).toHaveBeenLastCalledWith(4);
    expect(nav.textContent).toContain("Showing 41 to 42 of 42 entries");
  });

  it("jumps to a typed page on Enter, clamped, and resets on Escape or blur", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={2}
        pageSize={10}
        total={42}
        onPageChange={onPageChange}
      />,
    );
    const input = screen.getByRole("textbox", { name: "Page number, 1 to 5" });
    expect((input as HTMLInputElement).value).toBe("2");
    await user.clear(input);
    await user.type(input, "4");
    expect(onPageChange).not.toHaveBeenCalled();
    await user.keyboard("{Enter}");
    expect(onPageChange).toHaveBeenLastCalledWith(4);
    await user.clear(input);
    await user.type(input, "99{Enter}");
    expect(onPageChange).toHaveBeenLastCalledWith(5);
    await user.clear(input);
    await user.type(input, "abc{Enter}");
    expect(onPageChange).toHaveBeenCalledTimes(2);
    expect((input as HTMLInputElement).value).toBe("2");
    await user.clear(input);
    await user.type(input, "3{Escape}");
    expect((input as HTMLInputElement).value).toBe("2");
    await user.clear(input);
    await user.type(input, "3");
    await user.tab();
    expect((input as HTMLInputElement).value).toBe("2");
    // Typing the current page changes nothing.
    await user.clear(input);
    await user.type(input, "2{Enter}");
    expect(onPageChange).toHaveBeenCalledTimes(2);
  });

  it("changes the page size from the select", async () => {
    const user = userEvent.setup();
    const onPageSizeChange = vi.fn();
    const { rerender } = render(
      <Pagination page={1} pageSize={10} total={42} onPageChange={vi.fn()} />,
    );
    expect(screen.queryByRole("combobox")).toBeNull();
    rerender(
      <Pagination
        page={1}
        pageSize={25}
        total={42}
        onPageChange={vi.fn()}
        onPageSizeChange={onPageSizeChange}
      />,
    );
    const select = screen.getByRole("combobox", { name: "Rows per page" });
    // A size outside the options is still shown, in order.
    expect(
      within(select)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["10", "20", "25", "50", "100"]);
    await user.selectOptions(select, "50");
    expect(onPageSizeChange).toHaveBeenLastCalledWith(50);
  });

  it("clamps an out-of-range page and disables the box with one page", () => {
    render(
      <Pagination page={9} pageSize={10} total={0} onPageChange={vi.fn()} />,
    );
    const input = screen.getByRole("textbox", {
      name: "Page number, 1 to 1",
    }) as HTMLInputElement;
    expect(input.value).toBe("1");
    expect(input.disabled).toBe(true);
    expect(screen.getByText("No entries")).toBeTruthy();
  });
});

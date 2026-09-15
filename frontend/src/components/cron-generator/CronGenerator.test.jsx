import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import cronstrue from "cronstrue";
import { describe, expect, it, vi } from "vitest";

import { Modal } from "@/components/ui/shims/antd-overlays";
import CronGenerator from "./CronGenerator";

/**
 * This replaced `react-js-cron` — the last thing pulling antd into the tree.
 * The contract that matters is narrow: emit a valid 5-field cron string
 * through `setCronValue`, because the call-site (EtlTaskDeploy) feeds that
 * straight to cronstrue for its summary and to the backend as the schedule.
 *
 * So the assertions round-trip through cronstrue rather than string-matching:
 * "the expression means what the user picked" is the real property, and it is
 * checked by the same parser production uses.
 */

function open(props = {}) {
  const setCronValue = vi.fn();
  const showCronGenerator = vi.fn();
  render(
    <CronGenerator
      open
      setCronValue={setCronValue}
      showCronGenerator={showCronGenerator}
      {...props}
    />,
  );
  return { setCronValue, showCronGenerator };
}

const pick = (label, value) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

const confirm = () =>
  fireEvent.click(screen.getByRole("button", { name: "OK" }));

describe("CronGenerator", () => {
  it("defaults to hourly and emits a valid expression", () => {
    const { setCronValue } = open();
    confirm();
    expect(setCronValue).toHaveBeenCalledWith("0 * * * *");
    expect(cronstrue.toString("0 * * * *")).toMatch(/every hour/i);
  });

  it("builds a daily schedule at the chosen time", () => {
    const { setCronValue } = open();
    pick("Repeat", "day");
    pick("Hour", "9");
    pick("Minute", "30");
    confirm();

    const [expression] = setCronValue.mock.calls[0];
    expect(expression).toBe("30 9 * * *");
    // The user picked 09:30 daily — assert the MEANING, not the string.
    expect(cronstrue.toString(expression)).toMatch(/09:30 AM/);
  });

  it("builds a weekly schedule on the chosen weekday", () => {
    const { setCronValue } = open();
    pick("Repeat", "week");
    pick("On", "3");
    pick("Hour", "6");
    pick("Minute", "0");
    confirm();

    const [expression] = setCronValue.mock.calls[0];
    expect(expression).toBe("0 6 * * 3");
    expect(cronstrue.toString(expression)).toMatch(/wednesday/i);
  });

  it("builds a monthly schedule on the chosen day", () => {
    const { setCronValue } = open();
    pick("Repeat", "month");
    pick("Day of month", "15");
    pick("Hour", "1");
    pick("Minute", "5");
    confirm();

    const [expression] = setCronValue.mock.calls[0];
    expect(expression).toBe("5 1 15 * *");
    expect(cronstrue.toString(expression)).toMatch(/15/);
  });

  it("accepts a custom expression", () => {
    const { setCronValue } = open();
    pick("Repeat", "custom");
    fireEvent.change(screen.getByLabelText("Cron expression"), {
      target: { value: "*/15 2 * * 1-5" },
    });
    confirm();
    expect(setCronValue).toHaveBeenCalledWith("*/15 2 * * 1-5");
  });

  // A schedule the backend would reject must not escape the dialog.
  it("refuses to emit an invalid custom expression", () => {
    const { setCronValue, showCronGenerator } = open();
    pick("Repeat", "custom");
    fireEvent.change(screen.getByLabelText("Cron expression"), {
      target: { value: "not a cron" },
    });

    expect(screen.getByText(/not a valid cron/i)).toBeInTheDocument();
    confirm();
    expect(setCronValue).not.toHaveBeenCalled();
    expect(showCronGenerator).not.toHaveBeenCalled();
  });

  it("shows a live human-readable summary", () => {
    open();
    pick("Repeat", "day");
    pick("Hour", "13");
    pick("Minute", "45");
    expect(screen.getByText("45 13 * * *")).toBeInTheDocument();
    // cronstrue renders 12-hour time, so 13:45 reads as "01:45 PM".
    expect(screen.getByText(/01:45 PM/)).toBeInTheDocument();
  });

  it("closes without emitting on cancel", () => {
    const { setCronValue, showCronGenerator } = open();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(showCronGenerator).toHaveBeenCalledWith(false);
    expect(setCronValue).not.toHaveBeenCalled();
  });
});

/**
 * The call-site renders <CronGenerator> as a sibling AFTER EtlTaskDeploy's own
 * </Modal>, so in production this is two stacked Radix dialogs. The existing
 * scroll-lock test covers ONE dialog's lifecycle; two is a different case, and
 * P0-12 (body overflow) is exactly the invariant a nested dialog can break on
 * unmount.
 */
describe("CronGenerator nested inside another Modal", () => {
  function Stack({ innerOpen }) {
    return (
      <>
        <Modal open title="Deploy">
          outer body
        </Modal>
        {innerOpen && (
          <CronGenerator
            open
            setCronValue={() => undefined}
            showCronGenerator={() => undefined}
          />
        )}
      </>
    );
  }

  it("renders over the outer dialog and stays interactive", async () => {
    render(<Stack innerOpen />);
    expect(screen.getByText("outer body")).toBeInTheDocument();
    expect(screen.getByText("Choose Cron schedule")).toBeInTheDocument();

    // Inert Radix triggers have bitten this migration twice; prove the inner
    // dialog's controls actually respond.
    pick("Repeat", "week");
    expect(screen.getByLabelText("On")).toBeInTheDocument();
  });

  it("leaves the outer dialog open when the inner one closes", async () => {
    const { rerender } = render(<Stack innerOpen />);
    rerender(<Stack innerOpen={false} />);

    await waitFor(() =>
      expect(
        screen.queryByText("Choose Cron schedule"),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByText("outer body")).toBeInTheDocument();
  });

  it("keeps body overflow hidden after the inner dialog unmounts (P0-12)", async () => {
    document.body.style.overflow = "hidden";
    const { rerender } = render(<Stack innerOpen />);
    rerender(<Stack innerOpen={false} />);

    await waitFor(() =>
      expect(
        screen.queryByText("Choose Cron schedule"),
      ).not.toBeInTheDocument(),
    );
    // The regression: the inner dialog's cleanup restoring "" or "visible"
    // would make the fixed app shell scrollable behind the outer dialog.
    expect(document.body.style.overflow).toBe("hidden");
    document.body.style.overflow = "";
  });
});

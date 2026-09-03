import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The Configure Connector modal's file browser.
 *
 * `Tree.DirectoryTree` was never defined on the Tree shim, so the module-scope
 * `const { DirectoryTree } = Tree` resolved to undefined and rendering it threw
 * React #130 — which took down the whole workflow page ("Couldn't load this
 * page") the moment any FILESYSTEM connector was picked for an ETL pipeline.
 *
 * The shim-completeness guard missed it because it only read `<Foo.Bar>` and
 * `Foo.bar(` from the source, not the destructured form used here.
 */
const getFileList = vi.fn();

vi.mock("../../input-output/input-output/input-service.js", () => ({
  inputService: () => ({ getFileList }),
}));

vi.mock("../../../hooks/useExceptionHandler", () => ({
  useExceptionHandler: () => (err, fallback) => ({ content: fallback }),
}));

/*
 * The real icons are `*.svg?react` imports, which only become components once
 * vite-plugin-svgr runs. That plugin is not in the test pipeline, so unmocked
 * they resolve to data-URI strings and React renders each as an unknown tag.
 */
vi.mock("../../../assets", () => ({
  Document: () => <span data-testid="file-icon" />,
  Folder: () => <span data-testid="folder-icon" />,
}));

const { FileExplorer } = await import("./FileSystem.jsx");

const ROOT = [
  { name: "invoices", type: "directory", modified_at: "2026-08-01 10:00:00" },
  {
    name: "readme.txt",
    type: "file",
    size: 2048,
    modified_at: "2026-08-02 11:00:00",
  },
];

describe("FileExplorer", () => {
  beforeEach(() => {
    getFileList.mockReset();
  });

  it("renders the connector's files instead of throwing #130", () => {
    render(<FileExplorer selectedConnector="conn-1" data={ROOT} />);
    expect(screen.getByText("invoices")).toBeInTheDocument();
    expect(screen.getByText("readme.txt")).toBeInTheDocument();
  });

  it("shows the size and modified date columns", () => {
    render(<FileExplorer selectedConnector="conn-1" data={ROOT} />);
    expect(screen.getByText("2 KB")).toBeInTheDocument();
    expect(screen.getByText("2026-08-02")).toBeInTheDocument();
  });

  it("reports a picked folder as a folder and a picked file as a file", async () => {
    const onFolderSelect = vi.fn();
    render(
      <FileExplorer
        selectedConnector="conn-1"
        data={ROOT}
        onFolderSelect={onFolderSelect}
      />,
    );

    await userEvent.click(screen.getByText("invoices"));
    expect(onFolderSelect).toHaveBeenLastCalledWith("invoices", "folder");

    await userEvent.click(screen.getByText("readme.txt"));
    expect(onFolderSelect).toHaveBeenLastCalledWith("readme.txt", "file");
  });

  /*
   * Directories come back from the connector without their children — the
   * browser fetches one level at a time. Without loadData wired through, every
   * folder in the tree is permanently unopenable.
   */
  it("fetches a directory's children the first time it is expanded", async () => {
    getFileList.mockResolvedValue({
      data: [
        {
          name: "invoices/jan.pdf",
          type: "file",
          size: 512,
          modified_at: "2026-08-03 09:00:00",
        },
      ],
    });

    render(<FileExplorer selectedConnector="conn-1" data={ROOT} />);
    expect(screen.queryByText("jan.pdf")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Expand" }));

    expect(getFileList).toHaveBeenCalledWith("conn-1", "invoices");
    expect(await screen.findByText("jan.pdf")).toBeInTheDocument();
  });

  it("surfaces a load error rather than leaving the folder silently empty", async () => {
    getFileList.mockRejectedValue(new Error("boom"));
    const setError = vi.fn();

    render(
      <FileExplorer
        selectedConnector="conn-1"
        data={ROOT}
        setError={setError}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Expand" }));

    await waitFor(() => {
      expect(setError).toHaveBeenCalledWith(
        'Error loading files from "invoices"',
      );
    });
  });
});

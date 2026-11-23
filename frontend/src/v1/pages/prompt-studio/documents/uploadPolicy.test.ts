import { describe, expect, it } from "vitest";
import {
  acceptAttribute,
  OSS_UPLOAD_POLICY,
  planUploads,
  policyCaption,
  profileGate,
  type UploadPolicy,
} from "./uploadPolicy";

const MB = 1024 * 1024;
const pdf = (name: string, bytes = 10) =>
  new File([new Uint8Array(bytes)], name, { type: "application/pdf" });

const WIDE: UploadPolicy = {
  types: [
    { label: "PDF", extensions: ["pdf"] },
    { label: "DOCX", extensions: ["doc", "docx"] },
    { label: "PNG", extensions: ["png"] },
  ],
  maxBytes: 20 * MB,
};

it("matches the backend: PDF only, up to 200 MB", () => {
  expect(OSS_UPLOAD_POLICY.maxBytes).toBe(200 * MB);
  expect(OSS_UPLOAD_POLICY.types.flatMap((type) => type.extensions)).toEqual([
    "pdf",
  ]);
});

it("names the types and the limit in the drop zone caption", () => {
  expect(policyCaption(OSS_UPLOAD_POLICY)).toBe("Supports PDF · up to 200 MB");
  expect(policyCaption(WIDE)).toBe("Supports PDF, DOCX, PNG · up to 20 MB");
});

it("offers the allowed extensions to the file picker", () => {
  expect(acceptAttribute(WIDE)).toBe(".pdf,.doc,.docx,.png");
});

describe("planUploads", () => {
  it("accepts allowed files", () => {
    const file = pdf("a.pdf");
    expect(planUploads([file], OSS_UPLOAD_POLICY, [])).toEqual({
      accepted: [file],
      refused: [],
    });
  });

  it("refuses a type the policy does not take, by extension, in any case", () => {
    const plan = planUploads(
      [new File(["x"], "scan.png", { type: "image/png" }), pdf("UP.PDF")],
      OSS_UPLOAD_POLICY,
      [],
    );
    expect(plan.accepted.map((file) => file.name)).toEqual(["UP.PDF"]);
    expect(plan.refused).toEqual([
      {
        name: "scan.png",
        reason: "scan.png is not a supported type. Upload PDF.",
      },
    ]);
  });

  it("refuses a file without an extension", () => {
    const plan = planUploads([pdf("README")], OSS_UPLOAD_POLICY, []);
    expect(plan.refused[0]?.reason).toBe(
      "README is not a supported type. Upload PDF.",
    );
  });

  it("refuses a file over the limit and accepts one exactly at it", () => {
    const policy: UploadPolicy = { ...OSS_UPLOAD_POLICY, maxBytes: 100 };
    const plan = planUploads(
      [pdf("big.pdf", 101), pdf("edge.pdf", 100)],
      policy,
      [],
    );
    expect(plan.accepted.map((file) => file.name)).toEqual(["edge.pdf"]);
    expect(plan.refused).toEqual([
      { name: "big.pdf", reason: "big.pdf is larger than 100 B." },
    ]);
  });

  it("refuses a name already taken, ignoring the extension, as v0 does", () => {
    const plan = planUploads([pdf("statement.pdf")], WIDE, ["Statement.docx"]);
    expect(plan.refused).toEqual([
      {
        name: "statement.pdf",
        reason: "A document named statement already exists.",
      },
    ]);
  });

  it("refuses the second of two files with one name in one drop", () => {
    const plan = planUploads(
      [pdf("a.pdf"), pdf("a.pdf")],
      OSS_UPLOAD_POLICY,
      [],
    );
    expect(plan.accepted).toHaveLength(1);
    expect(plan.refused).toHaveLength(1);
  });
});

describe("profileGate", () => {
  it("asks for a profile when the tool has none", () => {
    expect(profileGate([])).toBe(
      "Add an LLM profile before uploading a document",
    );
  });

  it("asks for a default when no profile is the default", () => {
    expect(profileGate([{ is_default: false }])).toBe(
      "Set the default LLM profile before uploading a document",
    );
  });

  it("allows uploads once a default exists", () => {
    expect(
      profileGate([{ is_default: false }, { is_default: true }]),
    ).toBeNull();
  });
});

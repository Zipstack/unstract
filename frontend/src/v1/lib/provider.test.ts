import { expect, it } from "vitest";
import { iconSource, providerKey } from "./provider";

it("takes the provider key from an adapter or connector id", () => {
  expect(providerKey("openai|502ecf49-0e43-4b3c-a8a8-6b1c6c2b2c1f")).toBe(
    "openai",
  );
  expect(providerKey("noOpVectorDb|1")).toBe("noOpVectorDb");
  expect(providerKey("gdrive")).toBe("gdrive");
});

it("accepts paths and image URLs as icon sources", () => {
  expect(iconSource("/icons/adapter-icons/OpenAI.png")).toBe(
    "/icons/adapter-icons/OpenAI.png",
  );
  expect(iconSource("https://cdn.example.com/a.svg")).toBe(
    "https://cdn.example.com/a.svg",
  );
  expect(iconSource("data:image/png;base64,AAAA")).toBe(
    "data:image/png;base64,AAAA",
  );
});

it("treats the unavailable-icon marker and other non-URLs as missing", () => {
  expect(iconSource("⚠️")).toBeNull();
  expect(iconSource("")).toBeNull();
  expect(iconSource("   ")).toBeNull();
  expect(iconSource(null)).toBeNull();
  expect(iconSource(undefined)).toBeNull();
  expect(iconSource("javascript:alert(1)")).toBeNull();
});

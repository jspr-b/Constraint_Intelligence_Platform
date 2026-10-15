import { describe, expect, it } from "vitest";
import { UI_VERSION } from "./index";

describe("ui package", () => {
  it("exports a version", () => {
    expect(UI_VERSION).toBe("0.0.0");
  });
});

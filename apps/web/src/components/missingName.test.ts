import { describe, expect, it } from "vitest";
import en from "../../messages/en.json";
import { missingName } from "../lib/inputNames";

const names = en.figure.inputNames as Record<string, string>;
const t = Object.assign((key: string) => names[key.replace("inputNames.", "")] ?? key, {
  has: (key: string) => key.replace("inputNames.", "") in names,
});

describe("missing values on screen", () => {
  it("are named in plain words, never as a raw field name", () => {
    expect(missingName(t, "ideal_min")).toBe("Standard time");
    expect(missingName(t, "some_new_value_min")).toBe("some new value");
    expect(missingName(t, "sales prices")).toBe("sales prices");
  });
});

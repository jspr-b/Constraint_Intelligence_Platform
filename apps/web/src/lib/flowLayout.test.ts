import { describe, expect, it } from "vitest";
import {
  CARD_H,
  CARD_W,
  INPUT,
  OUTPUT,
  autoLayout,
  dotCount,
  lineWidth,
  moveAside,
  routeArrows,
  type LayoutArrow,
} from "./flowLayout";

/** A value that must be there; the test fails with its key otherwise. */
function get<T>(record: Record<string, T>, key: string): T {
  const value = record[key];
  if (value === undefined) throw new Error(`missing ${key}`);
  return value;
}

const steps = [
  { code: "CUT-01", station: "S1" },
  { code: "WLD-01", station: "S2" },
  { code: "WLD-02", station: "S2" },
  { code: "PNT-01", station: null },
];
const arrows: LayoutArrow[] = [
  { id: "a", from: "CUT-01", to: "WLD-01", rework: false },
  { id: "b", from: "CUT-01", to: "WLD-02", rework: false },
  { id: "c", from: "WLD-01", to: "PNT-01", rework: false },
  { id: "d", from: "PNT-01", to: "WLD-02", rework: true },
  { id: "e", from: "CUT-01", to: "PNT-01", rework: false },
];

describe("autoLayout", () => {
  const pos = autoLayout(steps, arrows);
  it("puts columns in flow order, left to right, between Input and Output", () => {
    expect(get(pos, INPUT).x).toBeLessThan(get(pos, "CUT-01").x);
    expect(get(pos, "CUT-01").x).toBeLessThan(get(pos, "WLD-01").x);
    expect(get(pos, "WLD-01").x).toBeLessThan(get(pos, "PNT-01").x);
    expect(get(pos, "PNT-01").x).toBeLessThan(get(pos, OUTPUT).x);
  });
  it("stacks a station's steps in one column, on the 8 px grid, without overlap", () => {
    expect(get(pos, "WLD-01").x).toBe(get(pos, "WLD-02").x);
    expect(Math.abs(get(pos, "WLD-01").y - get(pos, "WLD-02").y)).toBeGreaterThanOrEqual(CARD_H);
    for (const p of Object.values(pos)) {
      expect(p.x % 8).toBe(0);
      expect(p.y % 8).toBe(0);
    }
  });
});

describe("routeArrows", () => {
  const pos = autoLayout(steps, arrows);
  const routes = routeArrows(pos, arrows);
  it("sends rework through the lane below all cards", () => {
    const bottom = Math.max(...Object.values(pos).map((p) => p.y + CARD_H));
    expect(get(routes, "d").lane).toBe("under");
    expect(get(routes, "d").label.y).toBeGreaterThan(bottom);
  });
  it("runs between stacked cards without crossing them", () => {
    expect(get(routes, "e").lane).toBe("direct");
  });
  it("sends an arrow that would cross a card over the lane above", () => {
    const line = [
      { code: "A1", station: null },
      { code: "B1", station: null },
      { code: "C1", station: null },
    ];
    const skip: LayoutArrow[] = [
      { id: "ab", from: "A1", to: "B1", rework: false },
      { id: "bc", from: "B1", to: "C1", rework: false },
      { id: "ac", from: "A1", to: "C1", rework: false },
    ];
    const p = autoLayout(line, skip);
    const r = routeArrows(p, skip);
    const top = Math.min(...Object.values(p).map((q) => q.y));
    expect(get(r, "ac").lane).toBe("over");
    expect(get(r, "ac").label.y).toBeLessThan(top);
    expect(get(r, "ab").lane).toBe("direct");
  });
  it("joins steps stacked in one station with a short arrow", () => {
    const p = autoLayout(
      [
        { code: "W1", station: "S" },
        { code: "W2", station: "S" },
      ],
      [{ id: "w", from: "W1", to: "W2", rework: false }],
    );
    const r = routeArrows(p, [{ id: "w", from: "W1", to: "W2", rework: false }]);
    expect(get(r, "w").lane).toBe("stacked");
    expect(get(r, "w").label.y).toBeGreaterThan(get(p, "W1").y + CARD_H);
    expect(get(r, "w").label.y).toBeLessThan(get(p, "W2").y);
  });
  it("draws neighbours directly with right angles", () => {
    expect(get(routes, "a").lane).toBe("direct");
    expect(get(routes, "a").d).toMatch(/^M/);
  });
});

describe("moveAside", () => {
  it("moves a card dropped on another until it is free", () => {
    const out = moveAside({ A: { x: 0, y: 0 }, B: { x: 4, y: 4 } }, "B");
    expect(get(out, "B").y).toBeGreaterThanOrEqual(CARD_H);
    expect(get(out, "B").x % 8).toBe(0);
    expect(CARD_W).toBeGreaterThan(0);
  });
});

describe("motion and weight", () => {
  it("shows more dots where more jobs go, at least one", () => {
    expect(dotCount(null)).toBe(1);
    expect(dotCount(5)).toBe(1);
    expect(dotCount(70)).toBe(5);
  });
  it("varies line weight only slightly", () => {
    expect(lineWidth(100)).toBeLessThanOrEqual(2.2);
    expect(lineWidth(1)).toBeGreaterThanOrEqual(1);
  });
});

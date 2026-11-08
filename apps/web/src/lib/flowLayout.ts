/**
 * Layout and routing of the plant flow canvas (CI0005 seq 06, approved mockup).
 *
 * Geometry only: positions, lanes and paths. Every share and count comes from the engine
 * (GET /plants/{code}/flow); nothing here calculates a figure.
 */

export const CARD_W = 136;
export const CARD_H = 56;
export const GRID = 8;
const COL_GAP = 72;
const ROW_GAP = 48;
const STATION_PAD = 16;
const STATION_LABEL = 16;
const LANE_GAP = 22;
const CORNER = 7;

export const INPUT = "__input";
export const OUTPUT = "__output";

export interface Pos {
  x: number;
  y: number;
}

export interface LayoutStep {
  code: string;
  station: string | null;
}

export interface LayoutArrow {
  id: string;
  from: string;
  to: string;
  rework: boolean;
}

export type Positions = Record<string, Pos>;

const snap = (v: number) => Math.round(v / GRID) * GRID;

/**
 * Columns in flow order: a step's column is its longest forward path from Input (rework
 * arrows left out); a station's steps share the column of its earliest step and are stacked.
 */
export function autoLayout(steps: LayoutStep[], arrows: LayoutArrow[]): Positions {
  const codes = new Set(steps.map((s) => s.code));
  const forward = arrows.filter((a) => !a.rework && codes.has(a.from) && codes.has(a.to));
  const depth = new Map<string, number>(steps.map((s) => [s.code, 0]));
  // Longest path by relaxation; capped so a cycle the engine did not mark as rework still ends.
  for (let round = 0; round < steps.length; round++) {
    let moved = false;
    for (const a of forward) {
      const next = (depth.get(a.from) ?? 0) + 1;
      if (next > (depth.get(a.to) ?? 0) && next <= steps.length) {
        depth.set(a.to, next);
        moved = true;
      }
    }
    if (!moved) break;
  }
  const group = (s: LayoutStep) => s.station ?? `step:${s.code}`;
  const groups = new Map<string, LayoutStep[]>();
  for (const s of steps) groups.set(group(s), [...(groups.get(group(s)) ?? []), s]);
  const groupDepth = (members: LayoutStep[]) =>
    Math.min(...members.map((m) => depth.get(m.code) ?? 0));
  const ordered = [...groups.entries()].sort(
    ([ka, a], [kb, b]) => groupDepth(a) - groupDepth(b) || ka.localeCompare(kb),
  );
  // Groups at the same depth go in their own columns, one after the other.
  const tallest = Math.max(1, ...ordered.map(([, m]) => m.length));
  const height = tallest * (CARD_H + ROW_GAP) - ROW_GAP;
  const top = 96;
  const out: Positions = {};
  let x = 0;
  out[INPUT] = { x, y: snap(top + height / 2 - CARD_H / 2) };
  x += CARD_W + COL_GAP;
  for (const [, members] of ordered) {
    const sorted = [...members].sort((a, b) => a.code.localeCompare(b.code));
    const h = sorted.length * (CARD_H + ROW_GAP) - ROW_GAP;
    sorted.forEach((m, i) => {
      out[m.code] = {
        x: snap(x + STATION_PAD),
        y: snap(top + (height - h) / 2 + i * (CARD_H + ROW_GAP)),
      };
    });
    x += CARD_W + STATION_PAD * 2 + COL_GAP;
  }
  out[OUTPUT] = { x: snap(x), y: out[INPUT].y };
  return out;
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A station's box around its steps. */
export function stationBox(members: Pos[]): Box | null {
  if (!members.length) return null;
  const x1 = Math.min(...members.map((p) => p.x)) - STATION_PAD;
  const y1 = Math.min(...members.map((p) => p.y)) - STATION_PAD - STATION_LABEL;
  const x2 = Math.max(...members.map((p) => p.x + CARD_W)) + STATION_PAD;
  const y2 = Math.max(...members.map((p) => p.y + CARD_H)) + STATION_PAD;
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
}

const overlaps = (a: Pos, b: Pos) =>
  a.x < b.x + CARD_W && a.x + CARD_W > b.x && a.y < b.y + CARD_H && a.y + CARD_H > b.y;

/** A card dropped on another moves aside (down, on the grid) until it is free. */
export function moveAside(positions: Positions, id: string): Positions {
  const p = positions[id];
  if (!p) return positions;
  const others = Object.entries(positions)
    .filter(([k]) => k !== id)
    .map(([, v]) => v);
  let at = { x: snap(p.x), y: snap(p.y) };
  for (let i = 0; i < 200 && others.some((o) => overlaps(at, o)); i++) {
    at = { x: at.x, y: at.y + GRID };
  }
  return { ...positions, [id]: at };
}

/** Rounded right-angled path through the points. */
export function rounded(points: [number, number][], r = CORNER): string {
  const at = (i: number): [number, number] => points[i] ?? [0, 0];
  let d = `M${at(0)[0]},${at(0)[1]}`;
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = at(i - 1);
    const [cx, cy] = at(i);
    const [nx, ny] = at(i + 1);
    const l1 = Math.hypot(cx - px, cy - py);
    const l2 = Math.hypot(nx - cx, ny - cy);
    if (!l1 || !l2) continue;
    const k = Math.min(r, l1 / 2, l2 / 2);
    d += ` L${cx - ((cx - px) / l1) * k},${cy - ((cy - py) / l1) * k}`;
    d += ` Q${cx},${cy} ${cx + ((nx - cx) / l2) * k},${cy + ((ny - cy) / l2) * k}`;
  }
  const [lx, ly] = at(points.length - 1);
  return `${d} L${lx},${ly}`;
}

export interface Route {
  d: string;
  label: Pos;
  lane: "direct" | "over" | "under" | "stacked";
}

/**
 * Paths like a value stream map: straight runs between columns that never cross a card;
 * an arrow that would cross a card uses a lane above all cards, one going back (rework) a
 * lane below; each arrow has its own lane offset so routes do not stack.
 */
export function routeArrows(positions: Positions, arrows: LayoutArrow[]): Record<string, Route> {
  const cards = Object.entries(positions);
  if (!cards.length) return {};
  const top = Math.min(...cards.map(([, p]) => p.y)) - 40;
  const bottom = Math.max(...cards.map(([, p]) => p.y + CARD_H)) + 32;
  const blocked = (a: LayoutArrow, x1: number, x2: number, y1: number, y2: number) =>
    cards.some(
      ([k, c]) =>
        k !== a.from &&
        k !== a.to &&
        c.x < x2 &&
        c.x + CARD_W > x1 &&
        c.y < Math.max(y1, y2) + 6 &&
        c.y + CARD_H > Math.min(y1, y2) - 6,
    );
  const over: string[] = [];
  const under: string[] = [];
  for (const a of arrows) {
    const s = positions[a.from];
    const t = positions[a.to];
    if (!s || !t) continue;
    if (Math.abs(t.x - s.x) < CARD_W / 2 && t.y !== s.y) continue; // same column: stacked
    if (t.x <= s.x + CARD_W / 2) under.push(a.id);
    else if (blocked(a, s.x + CARD_W, t.x, s.y + CARD_H / 2, t.y + CARD_H / 2)) over.push(a.id);
  }
  const out: Record<string, Route> = {};
  for (const a of arrows) {
    const s = positions[a.from];
    const t = positions[a.to];
    if (!s || !t) continue;
    if (Math.abs(t.x - s.x) < CARD_W / 2 && t.y !== s.y) {
      // Steps stacked in one column (one station): a short arrow straight down or up.
      const down = t.y > s.y;
      const x = s.x + CARD_W / 2;
      const y1 = down ? s.y + CARD_H : s.y;
      const y2 = down ? t.y - 6 : t.y + CARD_H + 6;
      out[a.id] = { d: `M${x},${y1} L${x},${y2}`, label: { x, y: (y1 + y2) / 2 }, lane: "stacked" };
      continue;
    }
    const ui = under.indexOf(a.id);
    const oi = over.indexOf(a.id);
    if (ui >= 0) {
      const y = bottom + ui * LANE_GAP;
      const sx = s.x + CARD_W / 2 + 10;
      const ex = t.x + CARD_W / 2 - 10;
      out[a.id] = {
        d: rounded([
          [sx, s.y + CARD_H],
          [sx, y],
          [ex, y],
          [ex, t.y + CARD_H + 6],
        ]),
        label: { x: (sx + ex) / 2, y },
        lane: "under",
      };
      continue;
    }
    const sx = s.x + CARD_W;
    const sy = s.y + CARD_H / 2;
    const ex = t.x - 6;
    const ey = t.y + CARD_H / 2;
    if (oi >= 0) {
      const y = top - oi * LANE_GAP;
      const ox = sx + 14;
      const ix = t.x - 18;
      out[a.id] = {
        d: rounded([
          [sx, sy],
          [ox, sy],
          [ox, y],
          [ix, y],
          [ix, ey],
          [ex, ey],
        ]),
        label: { x: (ox + ix) / 2, y },
        lane: "over",
      };
      continue;
    }
    const mx = Math.round((sx + t.x) / 2);
    out[a.id] =
      Math.abs(sy - ey) < 2
        ? { d: `M${sx},${sy} L${ex},${ey}`, label: { x: mx, y: sy }, lane: "direct" }
        : {
            d: rounded([
              [sx, sy],
              [mx, sy],
              [mx, ey],
              [ex, ey],
            ]),
            label: { x: mx, y: (sy + ey) / 2 },
            lane: "direct",
          };
  }
  return out;
}

/** Moving dots on an arrow: about one per 14 % of jobs, at least one. */
export function dotCount(sharePct: number | null): number {
  return sharePct == null ? 1 : Math.max(1, Math.round(sharePct / 14));
}

/** Line weight varies only slightly with the share; arrowheads keep a fixed size. */
export function lineWidth(sharePct: number | null): number {
  return sharePct == null ? 1.2 : Math.max(1, Math.min(2.2, 1 + sharePct / 80));
}

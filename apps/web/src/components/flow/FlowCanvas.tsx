"use client";

import "@xyflow/react/dist/base.css";
import {
  EdgeLabelRenderer,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import { useLocale, useTranslations } from "next-intl";
import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";
import { Button, formatFigure } from "@cip/ui";
import {
  CARD_H,
  CARD_W,
  GRID,
  INPUT,
  OUTPUT,
  autoLayout,
  dotCount,
  lineWidth,
  moveAside,
  nearestRoute,
  pointAt,
  routeArrows,
  stationBox,
  type Box,
  type Pos,
  type Positions,
} from "@/lib/flowLayout";
import {
  buildModel,
  full,
  key,
  nextId,
  problems,
  upsert,
  type Arrow,
  type Edits,
  type Flow,
  type Model,
  type Resource,
} from "@/lib/flowModel";
import { Count } from "../Figure";
import { FlowPanel, type Form, type Sel } from "./FlowPanel";

type Hover = { step: string } | { arrow: string } | null;

/** Hover and selection for the canvas. Kept out of node and edge data: changing their data
 * on hover remounts edge labels in React Flow, which loses a click that is under way. */
interface CanvasApi {
  setHover: (h: Hover) => void;
  lit: { ids: Set<string>; cards: Set<string> } | null;
  sel: Sel | null;
  select: (s: Sel) => void;
  canEdit: boolean;
  issues: Set<string>;
  pickFrom: string | null;
}
const CanvasContext = createContext<CanvasApi>({
  setHover: () => undefined,
  lit: null,
  sel: null,
  select: () => undefined,
  canEdit: false,
  issues: new Set(),
  pickFrom: null,
});

type StepFields = {
  code: string;
  name: string;
  kind: string;
  jobs: number;
  missingFinish: number;
  measured: boolean;
  parallel: number;
  io: "input" | "output" | null;
};
type StepData = StepFields & Record<string, unknown>;

interface StationData extends Record<string, unknown> {
  code: string;
  name: string;
  w: number;
  h: number;
}

interface RouteData extends Record<string, unknown> {
  arrow: Arrow;
  d: string;
  points: [number, number][];
  label: { x: number; y: number };
  motion: boolean;
  touchpoints: { id: string; name: string; at: number }[];
}

const KIND_SHORT: Record<string, string> = {
  machine: "MCH",
  manual: "HND",
  check: "CHK",
  transport: "TRN",
  storage: "STO",
  station: "STN",
  work_centre: "WKC",
};

function StepCard({ data, selected }: NodeProps<Node<StepData>>) {
  const t = useTranslations("flowCanvas");
  const io = data.io;
  const { setHover, lit, canEdit, issues, pickFrom } = use(CanvasContext);
  const dim = lit !== null && !lit.cards.has(data.code);
  const issue = issues.has(data.code);
  const dot =
    "!h-2.5 !w-2.5 !rounded-full !border-[1.5px] !border-accent !bg-surface hover:!bg-accent";
  return (
    <div
      onPointerEnter={() => setHover({ step: data.code })}
      onPointerLeave={() => setHover(null)}
      className={`relative rounded-control border bg-surface px-2.5 py-2 transition-opacity duration-150 motion-reduce:transition-none ${
        selected || pickFrom === data.code
          ? "border-2 border-accent"
          : issue
            ? "border-2 border-warn"
            : "border-line-strong"
      } ${io ? "bg-raised" : ""} ${data.measured || io ? "" : "border-dashed"} ${dim ? "opacity-35" : ""}`}
      style={{ width: CARD_W, height: CARD_H }}
    >
      {io !== "input" && (
        <Handle
          type="target"
          position={Position.Left}
          isConnectable={canEdit}
          className={canEdit ? dot : "!opacity-0"}
          aria-label={t("dotIn", { step: data.code })}
        />
      )}
      {io ? (
        <>
          <div className="font-mono text-[9.5px] font-medium tracking-[0.06em] text-accent">
            {t(io)}
          </div>
          <div className="text-xs">{t(io === "input" ? "inputName" : "outputName")}</div>
          <div className="font-mono text-[11px] text-muted">{t("jobs", { n: data.jobs })}</div>
        </>
      ) : (
        <>
          <div className="flex justify-between font-mono text-xs font-medium">
            <span>
              {data.code}
              {data.parallel > 1 && ` ×${data.parallel}`}
            </span>
            <span className="text-[9.5px] tracking-[0.06em] text-muted">
              {KIND_SHORT[data.kind] ?? ""}
            </span>
          </div>
          <div className="truncate text-[11.5px] text-muted">{data.name}</div>
          {!data.measured ? (
            <div className="truncate text-[9.5px] font-medium tracking-[0.06em] text-warn">
              {t("notMeasuredTag")}
            </div>
          ) : (
            data.missingFinish > 0 && (
              <div className="truncate text-[9.5px] font-medium tracking-[0.06em] text-warn">
                {t("missingFinish", { n: data.missingFinish })}
              </div>
            )
          )}
        </>
      )}
      {io !== "output" && (
        <Handle
          type="source"
          position={Position.Right}
          isConnectable={canEdit}
          className={canEdit ? dot : "!opacity-0"}
          aria-label={t("dotOut", { step: data.code })}
        />
      )}
    </div>
  );
}

function StationBox({ data }: NodeProps<Node<StationData>>) {
  const { sel } = use(CanvasContext);
  const on = sel?.type === "station" && sel.id === data.code;
  return (
    <div
      className={`rounded-panel border bg-bg ${on ? "border-accent" : "border-line-strong"}`}
      style={{ width: data.w, height: data.h }}
    >
      <div className="cursor-grab px-2.5 pt-1 text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted">
        {data.name}
      </div>
    </div>
  );
}

function RouteEdge({ id, data }: EdgeProps<Edge<RouteData>>) {
  const t = useTranslations("flowCanvas");
  const locale = useLocale();
  const { setHover, lit, sel, select } = use(CanvasContext);
  if (!data) return null;
  const { arrow, d, label, motion, points, touchpoints } = data;
  const dim = lit !== null && !lit.ids.has(arrow.id);
  const on = sel?.type === "arrow" && sel.id === arrow.id;
  const pct = arrow.share && typeof arrow.share.value === "number" ? arrow.share.value : null;
  const share = arrow.share ? formatFigure(arrow.share, locale) : null;
  const base = arrow.wrong
    ? t("wrongTag")
    : arrow.kind === "measured"
      ? `${share}${arrow.rework ? ` ${t("rework")}` : ""}`
      : arrow.kind === "assumed"
        ? t("assumedTag", { share: share ?? "" })
        : arrow.kind === "estimate"
          ? t("estimateTag", { pct: arrow.estimatePct ?? 0 })
          : arrow.kind === "io"
            ? arrow.jobs != null
              ? t("jobs", { n: arrow.jobs })
              : t("newRoute")
            : t("newRoute");
  const text = arrow.name ? `${arrow.name} · ${base}` : base;
  const end = (c: string) => (c === INPUT ? t("input") : c === OUTPUT ? t("output") : c);
  const name = t("arrowLabel", { from: end(arrow.from), to: end(arrow.to) });
  const stroke = arrow.wrong
    ? "var(--color-bad)"
    : arrow.added || on
      ? "var(--color-accent)"
      : "var(--color-muted)";
  const dash = arrow.wrong ? "6 4" : arrow.added ? "2 3" : arrow.lessCertain ? "5 4" : undefined;
  const hollow = arrow.kind === "assumed" || arrow.kind === "estimate" || arrow.kind === "unknown";
  const n = arrow.kind === "unknown" ? 1 : dotCount(pct ?? arrow.estimatePct);
  const dur = 2.4;
  return (
    <>
      <g
        className={`transition-opacity duration-150 motion-reduce:transition-none ${dim ? "opacity-15" : ""}`}
        onPointerEnter={() => setHover({ arrow: arrow.id })}
        onPointerLeave={() => setHover(null)}
      >
        <path
          d={d}
          fill="none"
          stroke={stroke}
          strokeWidth={on ? 2.5 : lineWidth(pct)}
          strokeDasharray={dash}
          opacity={arrow.wrong ? 0.7 : 1}
          markerEnd="url(#cip-arrow)"
        />
        <path d={d} fill="none" stroke="transparent" strokeWidth={14} />
        {motion &&
          !arrow.wrong &&
          Array.from({ length: n }, (_, i) => (
            <circle
              key={`${id}-${i}`}
              r={2.6}
              fill={hollow ? "var(--color-surface)" : "var(--color-accent)"}
              stroke={hollow ? "var(--color-accent)" : undefined}
              strokeWidth={hollow ? 1.3 : undefined}
              opacity={arrow.lessCertain ? 0.45 : 1}
              aria-hidden="true"
            >
              <animateMotion
                dur={`${dur}s`}
                repeatCount="indefinite"
                begin={`${(-(dur * i) / n).toFixed(2)}s`}
                path={d}
              />
            </circle>
          ))}
      </g>
      <EdgeLabelRenderer>
        <button
          type="button"
          aria-label={`${name}: ${text}. ${t("openRoute")}`}
          aria-pressed={on}
          onPointerEnter={() => setHover({ arrow: arrow.id })}
          onPointerLeave={() => setHover(null)}
          onClick={() => select({ type: "arrow", id: arrow.id })}
          className={`nodrag nopan absolute cursor-pointer rounded-control border bg-surface px-1.5 font-mono text-[11px] transition-opacity duration-150 hover:border-accent motion-reduce:transition-none ${
            on ? "border-accent" : "border-line"
          } ${arrow.wrong ? "text-bad" : "text-text"} ${dim ? "opacity-15" : ""}`}
          style={{
            transform: `translate(-50%, -50%) translate(${label.x}px, ${label.y}px)`,
            pointerEvents: "all",
          }}
        >
          {text}
        </button>
        {touchpoints.map((tp) => {
          const p = pointAt(points, tp.at);
          const tsel = sel?.type === "touchpoint" && sel.id === tp.id;
          return (
            <button
              key={tp.id}
              type="button"
              aria-label={t("touchpointAria", { name: tp.name })}
              onClick={() => select({ type: "touchpoint", id: tp.id })}
              className={`nodrag nopan absolute flex cursor-pointer flex-col items-center border-0 bg-transparent p-0 ${dim ? "opacity-35" : ""}`}
              style={{
                transform: `translate(-50%, -100%) translate(${p.x}px, ${p.y + 6}px)`,
                pointerEvents: "all",
              }}
            >
              <span className="whitespace-nowrap text-[10px] text-muted">{tp.name}</span>
              <span
                className={`block h-3 w-3 rounded-full border-[1.5px] border-accent ${tsel ? "bg-accent" : "bg-surface"}`}
              />
            </button>
          );
        })}
      </EdgeLabelRenderer>
    </>
  );
}

/** Steps where a few jobs start or end, each count opening where it comes from. */
function RareEnds({ model }: { model: Model }) {
  const t = useTranslations("flowCanvas");
  const list = (items: { code: string; jobs: number }[], label: string, starts: boolean) =>
    items.length ? (
      <span>
        {label}{" "}
        {items.map((s, i) => (
          <span key={s.code}>
            {i > 0 && ", "}
            <span className="font-mono">{s.code}</span>{" "}
            <Count
              value={s.jobs}
              label={starts ? t("startHere") : t("endHere")}
              source={{ what: t("countSource"), href: "/data", page: t("dataPage") }}
            />
          </span>
        ))}
        .{" "}
      </span>
    ) : null;
  return (
    <>
      {list(model.rare.starts, t("rareStarts"), true)}
      {list(model.rare.ends, t("rareEnds"), false)}
    </>
  );
}

const NODE_TYPES = { step: StepCard, station: StationBox };
const EDGE_TYPES = { route: RouteEdge };
const EMPTY_STATION = { w: CARD_W + 32, h: CARD_H + 48 };

function reducedMotion(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

const inside = (p: Pos, b: Box) => p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h;

export interface FlowCanvasProps {
  flow: Flow;
  resources: Resource[];
  edits: Edits;
  canEdit: boolean;
  /** Save the whole edit document; resolves to an error message, or null when saved. */
  save: (edits: Edits, change: string) => Promise<string | null>;
}

function Canvas({ flow, resources, edits, canEdit, save }: FlowCanvasProps) {
  const t = useTranslations("flowCanvas");
  const rf = useReactFlow();
  const [doc, setDoc] = useState(() => full(edits));
  const saved = useRef(full(edits));
  const [past, setPast] = useState<Edits[]>([]);
  const [future, setFuture] = useState<Edits[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<Sel | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [connect, setConnect] = useState(false);
  const [pickFrom, setPickFrom] = useState<string | null>(null);
  const [hover, setHover] = useState<Hover>(null);
  const [motion, setMotion] = useState(() => !reducedMotion());
  const [fullScreen, setFullScreen] = useState(false);
  const [drag, setDrag] = useState<Positions>({});
  const [over, setOver] = useState(false);

  const model = useMemo(() => buildModel(flow, resources, doc), [flow, resources, doc]);
  const issues = useMemo(() => problems(model), [model]);
  const layout = useMemo(
    () =>
      autoLayout(
        model.steps.map((s) => ({ code: s.code, station: s.station })),
        model.arrows.map((a) => ({ id: a.id, from: a.from, to: a.to, rework: a.rework })),
      ),
    [model],
  );
  const stored = useMemo(
    () => Object.fromEntries(doc.positions.map((p) => [p.id, { x: p.x, y: p.y }])) as Positions,
    [doc.positions],
  );
  const positions: Positions = useMemo(
    () => ({ ...layout, ...stored, ...drag }),
    [layout, stored, drag],
  );

  /** Save an edit: the change is kept in history and sent whole; a refusal undoes it. */
  const commit = useCallback(
    (change: string, mutate: (d: Required<Edits>) => Required<Edits>) => {
      const before = saved.current;
      const next = mutate(full(doc));
      saved.current = next;
      setPast((p) => [...p.slice(-49), before]);
      setFuture([]);
      setDoc(next);
      setError(null);
      void save(next, change).then((problem) => {
        if (problem) {
          setError(problem);
          saved.current = before;
          setDoc(full(before));
          setPast((p) => p.slice(0, -1));
        }
      });
    },
    [doc, save],
  );
  /** Show a change while typing; ``commit`` saves it when the field is left. */
  const preview = useCallback((mutate: (d: Required<Edits>) => Required<Edits>) => {
    setDoc((d) => mutate(full(d)));
  }, []);
  const restore = (to: Edits, from: Edits, change: string) => {
    saved.current = full(to);
    setDoc(full(to));
    void save(to, change).then((problem) => {
      if (problem) {
        setError(problem);
        saved.current = full(from);
        setDoc(full(from));
      }
    });
  };
  const undo = () => {
    const last = past[past.length - 1];
    if (!last) return;
    setPast((p) => p.slice(0, -1));
    setFuture((f) => [...f, saved.current]);
    restore(last, saved.current, "undo");
  };
  const redo = () => {
    const next = future[future.length - 1];
    if (!next) return;
    setFuture((f) => f.slice(0, -1));
    setPast((p) => [...p, saved.current]);
    restore(next, saved.current, "redo");
  };
  /** Every card's place as it is now, so a change does not move what the client placed. */
  const frozen = (extra: Positions = {}) =>
    Object.entries({ ...positions, ...extra }).map(([id, p]) => ({ id, x: p.x, y: p.y }));

  const select = useCallback((s: Sel) => {
    setForm(null);
    setSel(s);
  }, []);

  useEffect(() => {
    if (!fullScreen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setFullScreen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullScreen]);
  useEffect(() => {
    const id = window.setTimeout(() => void rf.fitView({ padding: 0.1, duration: 0 }), 0);
    return () => window.clearTimeout(id);
  }, [fullScreen, rf]);

  const lit = useMemo(() => {
    if (!hover) return null;
    const ids = new Set<string>();
    const cards = new Set<string>();
    for (const a of model.arrows) {
      const on =
        "arrow" in hover ? a.id === hover.arrow : a.from === hover.step || a.to === hover.step;
      if (on) {
        ids.add(a.id);
        cards.add(a.from);
        cards.add(a.to);
      }
    }
    if ("step" in hover) cards.add(hover.step);
    return { ids, cards };
  }, [hover, model.arrows]);

  const api = useMemo(
    () => ({
      setHover,
      lit,
      sel,
      select,
      canEdit,
      issues: new Set(issues.map((p) => p.step)),
      pickFrom,
    }),
    [lit, sel, select, canEdit, issues, pickFrom],
  );

  const stations = useMemo(
    () =>
      model.stations.map((st) => {
        const members = model.steps.filter((s) => s.station === st.code).map((s) => s.code);
        const box =
          stationBox(members.flatMap((m) => (positions[m] ? [positions[m]] : []))) ??
          ({ ...(positions[`station:${st.code}`] ?? { x: 0, y: 0 }), ...EMPTY_STATION } as Box);
        return { ...st, members, box };
      }),
    [model, positions],
  );

  const nodes: Node[] = useMemo(() => {
    const out: Node[] = [];
    for (const st of stations) {
      out.push({
        id: `station:${st.code}`,
        type: "station",
        position: { x: st.box.x, y: st.box.y },
        data: { code: st.code, name: st.name, w: st.box.w, h: st.box.h },
        zIndex: -1,
        selectable: false,
        ariaLabel: t("stationAria", { name: st.name }),
      });
    }
    const card = (id: string, data: StepFields) =>
      out.push({
        id,
        type: "step",
        position: positions[id] ?? { x: 0, y: 0 },
        data,
        selected: sel?.type === "step" && sel.id === id,
        ariaLabel:
          data.io === "input"
            ? t("input")
            : data.io === "output"
              ? t("output")
              : t("stepAria", { code: data.code, name: data.name }),
      });
    const io = { name: "", kind: "", missingFinish: 0, measured: true, parallel: 1 };
    card(INPUT, { ...io, code: INPUT, jobs: flow.jobs, io: "input" });
    for (const s of model.steps) {
      card(s.code, {
        code: s.code,
        name: s.name,
        kind: s.kind,
        jobs: s.jobs,
        missingFinish: s.missingFinish,
        measured: s.measured,
        parallel: s.parallel,
        io: null,
      });
    }
    card(OUTPUT, { ...io, code: OUTPUT, jobs: flow.jobs, io: "output" });
    return out;
  }, [stations, model.steps, positions, flow.jobs, sel, t]);

  const routes = useMemo(
    () =>
      routeArrows(
        positions,
        model.arrows.map((a) => ({ id: a.id, from: a.from, to: a.to, rework: a.rework })),
      ),
    [positions, model.arrows],
  );
  const edges: Edge[] = useMemo(
    () =>
      model.arrows.flatMap((a) => {
        const r = routes[a.id];
        if (!r) return [];
        return [
          {
            id: a.id,
            source: a.from,
            target: a.to,
            type: "route",
            data: {
              arrow: a,
              d: r.d,
              points: r.points,
              label: r.label,
              motion,
              touchpoints: model.touchpoints.filter((tp) => tp.arrow === a.id),
            },
          },
        ];
      }),
    [model, routes, motion],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const c of changes) {
        if (c.type !== "position" || !c.position) continue;
        if (!canEdit) continue;
        const pos = c.position;
        let moves: Positions = {};
        if (c.id.startsWith("station:")) {
          const st = stations.find((s) => `station:${s.code}` === c.id);
          if (!st) continue;
          const dx = pos.x - st.box.x;
          const dy = pos.y - st.box.y;
          for (const m of st.members) {
            const p = positions[m];
            if (p) moves[m] = { x: p.x + dx, y: p.y + dy };
          }
          if (!st.members.length) moves[c.id] = pos;
        } else {
          moves = { [c.id]: pos };
        }
        if (c.dragging === false) {
          let all = { ...positions, ...moves };
          let change = "moved";
          let stationEdit: { code: string; station: string | null } | null = null;
          if (!c.id.startsWith("station:") && c.id !== INPUT && c.id !== OUTPUT) {
            all = moveAside(all, c.id);
            const p = all[c.id] ?? pos;
            const center = { x: p.x + CARD_W / 2, y: p.y + CARD_H / 2 };
            const step = model.steps.find((s) => s.code === c.id);
            // Dropped in another station's box: the step joins it; out of its own: none.
            const into = stations.find(
              (st) =>
                st.code !== step?.station &&
                inside(center, st.members.length ? st.box : { ...st.box }),
            );
            const own = stations.find((st) => st.code === step?.station);
            const others = own?.members.filter((m) => m !== c.id) ?? [];
            const ownBox = stationBox(others.flatMap((m) => (all[m] ? [all[m]] : [])));
            if (into) stationEdit = { code: c.id, station: into.code };
            else if (
              own &&
              ownBox &&
              !inside(center, {
                ...ownBox,
                x: ownBox.x - 24,
                y: ownBox.y - 24,
                w: ownBox.w + 48,
                h: ownBox.h + 48,
              })
            )
              stationEdit = { code: c.id, station: null };
          }
          const placed = Object.entries(all).map(([id, p]) => ({ id, x: p.x, y: p.y }));
          if (stationEdit) change = stationEdit.station ? "step_station" : "step_no_station";
          const se = stationEdit;
          setDrag({});
          commit(change, (d) => ({
            ...d,
            positions: placed,
            step_stations: se
              ? upsert(d.step_stations, (x) => x.code === se.code, {
                  code: se.code,
                  station_code: se.station,
                })
              : d.step_stations,
          }));
        } else {
          setDrag((prev) => ({ ...prev, ...moves }));
        }
      }
    },
    [canEdit, stations, positions, model.steps, commit],
  );

  const addRoute = useCallback(
    (from: string, to: string) => {
      if (from === to || to === INPUT || from === OUTPUT) return;
      if (model.arrows.some((a) => a.from === from && a.to === to)) {
        select({ type: "arrow", id: key(from, to) });
        return;
      }
      commit("route_added", (d) => ({
        ...d,
        routes_added: [
          ...d.routes_added,
          {
            route_id: nextId(
              "r",
              d.routes_added.map((r) => r.route_id),
            ),
            from_step: from,
            to_step: to,
          },
        ],
      }));
      setSel({ type: "arrow", id: key(from, to), focusName: true });
      setForm(null);
    },
    [commit, model.arrows, select],
  );
  const onConnect = useCallback(
    (c: Connection) => c.source && c.target && addRoute(c.source, c.target),
    [addRoute],
  );
  const onNodeClick = (_: unknown, node: Node) => {
    if (node.id.startsWith("station:")) {
      select({ type: "station", id: node.id.slice(8) });
      return;
    }
    if (connect && canEdit) {
      if (!pickFrom) setPickFrom(node.id);
      else {
        addRoute(pickFrom, node.id);
        setPickFrom(null);
        setConnect(false);
      }
      return;
    }
    if (node.id === INPUT || node.id === OUTPUT) select({ type: "io", id: node.id });
    else select({ type: "step", id: node.id });
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    if (!canEdit) return;
    const what = e.dataTransfer.getData("application/cip-add");
    const at = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    if (what === "step") {
      const under = stations.find((st) => inside(at, st.box));
      setSel(null);
      setForm({
        kind: "step",
        at: { x: at.x - CARD_W / 2, y: at.y - CARD_H / 2 },
        station: under?.code ?? null,
      });
    } else if (what === "touchpoint") {
      const id = nearestRoute(routes, at);
      if (id) {
        setSel({ type: "arrow", id });
        setForm({ kind: "touchpoint", arrow: id });
      }
    } else if (what === "station") {
      setSel(null);
      setForm({ kind: "station", at });
    }
  };
  const dragAdd = (what: string) => (e: DragEvent) => {
    e.dataTransfer.setData("application/cip-add", what);
    e.dataTransfer.effectAllowed = "copy";
  };

  const reorganize = () => commit("reorganized", (d) => ({ ...d, positions: [] }));
  const uncertain = model.arrows.filter((a) => a.lessCertain && !a.rework).length;

  const addButton = (what: "step" | "touchpoint" | "station", label: string) => (
    <div draggable={canEdit} onDragStart={dragAdd(what)} className="inline-flex">
      <Button
        isDisabled={!canEdit}
        onPress={() => {
          if (what === "touchpoint" && sel?.type === "arrow")
            setForm({ kind: "touchpoint", arrow: sel.id });
          else if (what === "touchpoint") setForm({ kind: "touchpoint", arrow: null });
          else setForm({ kind: what });
        }}
      >
        + {label}
      </Button>
    </div>
  );

  return (
    <div
      className={
        fullScreen
          ? "fixed inset-0 z-50 grid grid-rows-[auto_auto_1fr_auto] gap-2 overflow-auto bg-bg p-4"
          : "grid gap-2"
      }
      role={fullScreen ? "dialog" : undefined}
      aria-modal={fullScreen ? true : undefined}
      aria-label={fullScreen ? t("fullTitle") : undefined}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
        <span className="text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted">
          {t("strip")}
        </span>
        <div className="flex flex-wrap gap-1">
          <Button aria-pressed={motion} onPress={() => setMotion((m) => !m)}>
            {t("movement")}
          </Button>
          <Button onPress={reorganize} isDisabled={!canEdit}>
            {t("reorganize")}
          </Button>
          <Button aria-label={t("zoomOut")} onPress={() => void rf.zoomOut({ duration: 120 })}>
            −
          </Button>
          <Button onPress={() => void rf.fitView({ padding: 0.1, duration: 150 })}>
            {t("fit")}
          </Button>
          <Button aria-label={t("zoomIn")} onPress={() => void rf.zoomIn({ duration: 120 })}>
            +
          </Button>
          <Button aria-pressed={fullScreen} onPress={() => setFullScreen((f) => !f)}>
            {fullScreen ? t("closeFull") : t("full")}
          </Button>
        </div>
      </div>
      {canEdit && (
        <div
          className="flex flex-wrap items-center gap-1"
          role="toolbar"
          aria-label={t("editTools")}
        >
          <span className="mr-1 text-micro uppercase tracking-[var(--tracking-micro)] text-muted">
            {t("add")}
          </span>
          {addButton("step", t("step"))}
          {addButton("touchpoint", t("touchpoint"))}
          {addButton("station", t("station"))}
          <span className="mx-1 h-5 w-px bg-line" aria-hidden="true" />
          <Button
            aria-pressed={connect}
            onPress={() => {
              setConnect((c) => !c);
              setPickFrom(null);
            }}
          >
            {t("connect")}
          </Button>
          <Button onPress={undo} isDisabled={!past.length}>
            {t("undo")}
          </Button>
          <Button onPress={redo} isDisabled={!future.length}>
            {t("redo")}
          </Button>
          <Button
            onPress={() => commit("back_to_found", () => full(null))}
            isDisabled={JSON.stringify(full(doc)) === JSON.stringify(full(null))}
          >
            {t("backToFound")}
          </Button>
          <span className="text-xs text-muted">
            {connect ? (pickFrom ? t("connectTo") : t("connectFrom")) : t("addHint")}
          </span>
        </div>
      )}
      {error && (
        <p role="alert" className="m-0 border border-bad px-3 py-2 text-sm text-bad">
          {error}
        </p>
      )}
      <div
        className={`grid gap-2 ${fullScreen ? "grid-cols-[minmax(0,1fr)_300px]" : "lg:grid-cols-[minmax(0,1fr)_280px]"}`}
      >
        <div
          className={`relative rounded-panel border bg-surface ${over ? "border-accent border-dashed" : "border-line"} ${fullScreen ? "min-h-[60vh]" : "h-[520px]"}`}
          data-testid="flow-canvas"
          onDragOver={(e) => {
            if (!canEdit) return;
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <svg width="0" height="0" className="absolute" aria-hidden="true">
            <defs>
              <marker
                id="cip-arrow"
                viewBox="0 0 8 8"
                refX="1"
                refY="4"
                markerWidth="6"
                markerHeight="6"
                markerUnits="userSpaceOnUse"
                orient="auto"
              >
                <path d="M0,0 L8,4 L0,8 z" fill="var(--color-muted)" />
              </marker>
            </defs>
          </svg>
          <CanvasContext value={api}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              edgeTypes={EDGE_TYPES}
              onNodesChange={onNodesChange}
              onConnect={onConnect}
              onNodeClick={onNodeClick}
              onNodeDoubleClick={(_, node) =>
                node.id.startsWith("station:")
                  ? setSel({ type: "station", id: node.id.slice(8), focusName: true })
                  : node.id !== INPUT &&
                    node.id !== OUTPUT &&
                    setSel({ type: "step", id: node.id, focusName: true })
              }
              onPaneClick={() => {
                setSel(null);
                setPickFrom(null);
              }}
              nodesDraggable={canEdit}
              nodesConnectable={canEdit}
              snapToGrid
              snapGrid={[GRID, GRID]}
              edgesFocusable={false}
              zoomOnDoubleClick={false}
              minZoom={0.2}
              maxZoom={2}
              fitView
              proOptions={{ hideAttribution: true }}
              ariaLabelConfig={{ "node.a11yDescription.default": t("keyboardHelp") }}
            />
          </CanvasContext>
        </div>
        <FlowPanel
          flow={flow}
          model={model}
          doc={doc}
          sel={sel}
          form={form}
          issues={issues}
          canEdit={canEdit}
          select={(s) => {
            setForm(null);
            setSel(s);
          }}
          setForm={setForm}
          commit={commit}
          preview={preview}
          frozen={frozen}
          layoutOf={(code) => positions[code] ?? null}
        />
      </div>
      <Legend />
      <p className="m-0 text-xs text-muted">
        {t("hint")}
        {uncertain > 0 && ` ${t("uncertainSummary", { n: uncertain })}`}
        {flow.other_routes_jobs > 0 && ` ${t("otherRoutes", { n: flow.other_routes_jobs })}`}
      </p>
      <p className="m-0 text-xs text-muted">
        <RareEnds model={model} />
      </p>
    </div>
  );
}

function Legend() {
  const t = useTranslations("flowCanvas");
  const line = (stroke: string, dash?: string) => (
    <svg width="30" height="8" aria-hidden="true">
      <line x1="0" y1="4" x2="30" y2="4" stroke={stroke} strokeWidth="1.5" strokeDasharray={dash} />
    </svg>
  );
  return (
    <ul
      className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-xs text-muted"
      aria-label={t("legend")}
    >
      <li className="flex items-center gap-1.5">
        {line("var(--color-muted)")}
        {t("legendData")}
      </li>
      <li className="flex items-center gap-1.5">
        {line("var(--color-muted)", "5 4")}
        {t("legendUnsure")}
      </li>
      <li className="flex items-center gap-1.5">
        {line("var(--color-accent)", "2 3")}
        {t("legendAdded")}
      </li>
      <li className="flex items-center gap-1.5">
        {line("var(--color-bad)", "6 4")}
        {t("legendWrong")}
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="26" height="10" aria-hidden="true">
          <circle cx="6" cy="5" r="3" fill="var(--color-accent)" />
          <circle
            cx="19"
            cy="5"
            r="3"
            fill="var(--color-surface)"
            stroke="var(--color-accent)"
            strokeWidth="1.3"
          />
        </svg>
        {t("legendDots")}
      </li>
    </ul>
  );
}

/** The plant's flow found in the data, as an editable map (approved mockup, CI0005 seq 06). */
export function FlowCanvas(props: FlowCanvasProps) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}

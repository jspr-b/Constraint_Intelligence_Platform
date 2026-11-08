"use client";

import "@xyflow/react/dist/base.css";
import {
  EdgeLabelRenderer,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import { useLocale, useTranslations } from "next-intl";
import { createContext, use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, formatFigure } from "@cip/ui";
import type { components } from "@/lib/api/schema";
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
  routeArrows,
  stationBox,
  type LayoutArrow,
  type Positions,
} from "@/lib/flowLayout";
import { useDetails } from "../Details";
import { Count, HowCalculated } from "../Figure";

type Flow = components["schemas"]["FlowOut"];
type Resource = components["schemas"]["ResourceOut"];
type Share = Flow["arrows"][number]["share"];

interface Arrow extends LayoutArrow {
  jobs: number;
  share: Share | null;
  lessCertain: boolean;
  uncertainJobs: number;
}

type Hover = { step: string } | { arrow: string } | null;

/** Hover state for the canvas. Kept out of node and edge data: changing their data on hover
 * remounts edge labels in React Flow, which loses a click that is under way. */
interface HoverApi {
  setHover: (h: Hover) => void;
  lit: { ids: Set<string>; cards: Set<string> } | null;
}
const HoverContext = createContext<HoverApi>({ setHover: () => undefined, lit: null });

type StepFields = {
  code: string;
  name: string | null;
  kind: string | null;
  jobs: number;
  missingFinish: number;
  io: "input" | "output" | null;
};

type StepData = StepFields & Record<string, unknown>;

interface StationData extends Record<string, unknown> {
  name: string;
  w: number;
  h: number;
}

interface RouteData extends Record<string, unknown> {
  arrow: Arrow;
  d: string;
  label: { x: number; y: number };
  motion: boolean;
}

const KIND_SHORT: Record<string, string> = {
  machine: "MCH",
  manual: "HND",
  station: "STN",
  work_centre: "WKC",
};

function StepCard({ data, selected }: NodeProps<Node<StepData>>) {
  const t = useTranslations("flowCanvas");
  const io = data.io;
  const { setHover, lit } = use(HoverContext);
  const dim = lit !== null && !lit.cards.has(data.code);
  return (
    <div
      onPointerEnter={() => setHover({ step: data.code })}
      onPointerLeave={() => setHover(null)}
      className={`relative rounded-control border bg-surface px-2.5 py-2 transition-opacity duration-150 motion-reduce:transition-none ${
        selected ? "border-accent border-2" : "border-line-strong"
      } ${io ? "bg-raised" : ""} ${dim ? "opacity-35" : ""}`}
      style={{ width: CARD_W, height: CARD_H }}
    >
      {io !== "input" && <Handle type="target" position={Position.Left} className="!opacity-0" />}
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
            <span>{data.code}</span>
            <span className="text-[9.5px] tracking-[0.06em] text-muted">
              {data.kind ? (KIND_SHORT[data.kind] ?? "") : ""}
            </span>
          </div>
          <div className="truncate text-[11.5px] text-muted">{data.name ?? t("noName")}</div>
          {data.missingFinish > 0 && (
            <div className="truncate text-[9.5px] font-medium tracking-[0.06em] text-warn">
              {t("missingFinish", { n: data.missingFinish })}
            </div>
          )}
        </>
      )}
      {io !== "output" && <Handle type="source" position={Position.Right} className="!opacity-0" />}
    </div>
  );
}

function StationBox({ data }: NodeProps<Node<StationData>>) {
  return (
    <div
      className="rounded-panel border border-line-strong bg-bg"
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
  const details = useDetails();
  const { setHover, lit } = use(HoverContext);
  if (!data) return null;
  const { arrow, d, label, motion } = data;
  const dim = lit !== null && !lit.ids.has(arrow.id);
  const pct = arrow.share && typeof arrow.share.value === "number" ? arrow.share.value : null;
  const n = dotCount(pct);
  const dur = 2.4;
  const text = arrow.share
    ? `${formatFigure(arrow.share, locale)}${arrow.rework ? ` ${t("rework")}` : ""}`
    : t("jobs", { n: arrow.jobs });
  const end = (c: string) => (c === INPUT ? t("input") : c === OUTPUT ? t("output") : c);
  const name = t("arrowLabel", { from: end(arrow.from), to: end(arrow.to) });
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
          stroke="var(--color-muted)"
          strokeWidth={lineWidth(pct)}
          strokeDasharray={arrow.lessCertain ? "5 4" : undefined}
          markerEnd="url(#cip-arrow)"
        />
        <path d={d} fill="none" stroke="transparent" strokeWidth={14} />
        {motion &&
          Array.from({ length: n }, (_, i) => (
            <circle
              key={`${id}-${i}`}
              r={2.6}
              fill="var(--color-accent)"
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
          aria-label={`${name}: ${text}. ${t("openShare")}`}
          onPointerEnter={() => setHover({ arrow: arrow.id })}
          onPointerLeave={() => setHover(null)}
          onClick={() =>
            arrow.share
              ? details.show(<ShareDetails arrow={arrow} />)
              : details.show(<IoDetails arrow={arrow} />)
          }
          className={`nodrag nopan absolute cursor-pointer rounded-control border border-line bg-surface px-1.5 font-mono text-[11px] text-text transition-opacity duration-150 hover:border-accent motion-reduce:transition-none ${
            dim ? "opacity-15" : ""
          }`}
          style={{
            transform: `translate(-50%, -50%) translate(${label.x}px, ${label.y}px)`,
            pointerEvents: "all",
          }}
        >
          {text}
        </button>
      </EdgeLabelRenderer>
    </>
  );
}

function ShareDetails({ arrow }: { arrow: Arrow }) {
  const t = useTranslations("flowCanvas");
  return (
    <>
      {arrow.share && <HowCalculated figure={arrow.share} label={t("shareLabel")} />}
      <div className="flex flex-col gap-3 px-3 pb-3 text-sm">
        <p className="m-0 font-mono text-xs">
          {t("arrowLabel", { from: arrow.from, to: arrow.to })}
        </p>
        <p className="m-0 text-muted">{t("how", { from: arrow.from, to: arrow.to })}</p>
        {arrow.rework && <p className="m-0 text-muted">{t("reworkNote")}</p>}
        {arrow.lessCertain && (
          <p className="m-0 bg-raised px-2.5 py-2 text-muted">
            {arrow.rework && arrow.uncertainJobs === 0
              ? t("lessCertainRework")
              : t("lessCertainNote", { n: arrow.uncertainJobs })}
          </p>
        )}
      </div>
    </>
  );
}

function IoDetails({ arrow }: { arrow: Arrow }) {
  const t = useTranslations("flowCanvas");
  const into = arrow.from === INPUT;
  return (
    <div className="flex flex-col gap-3 p-3 text-sm">
      <p className="m-0">
        <Count
          value={arrow.jobs}
          label={into ? t("startHere") : t("endHere")}
          source={{ what: t("countSource"), href: "/data", page: t("dataPage") }}
        />{" "}
        {into ? t("startHereLong", { step: arrow.to }) : t("endHereLong", { step: arrow.from })}
      </p>
    </div>
  );
}

/** Below this share of jobs, a start or end is listed under the canvas instead of drawn. */
const IO_MIN_PCT = 5;

/** Steps where a few jobs start or end, each count opening where it comes from. */
function RareEnds({ flow }: { flow: Flow }) {
  const t = useTranslations("flowCanvas");
  const few = (n: number) => n > 0 && 100 * n < IO_MIN_PCT * flow.jobs;
  const list = (key: "first_jobs" | "last_jobs", label: string) => {
    const steps = flow.steps.filter((s) => few(s[key]));
    if (!steps.length) return null;
    return (
      <span>
        {label}{" "}
        {steps.map((s, i) => (
          <span key={s.code}>
            {i > 0 && ", "}
            <span className="font-mono">{s.code}</span>{" "}
            <Count
              value={s[key]}
              label={key === "first_jobs" ? t("startHere") : t("endHere")}
              source={{ what: t("countSource"), href: "/data", page: t("dataPage") }}
            />
          </span>
        ))}
        .{" "}
      </span>
    );
  };
  return (
    <>
      {list("first_jobs", t("rareStarts"))}
      {list("last_jobs", t("rareEnds"))}
    </>
  );
}

const NODE_TYPES = { step: StepCard, station: StationBox };
const EDGE_TYPES = { route: RouteEdge };

function reducedMotion(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

function Canvas({ flow, resources }: { flow: Flow; resources: Resource[] }) {
  const t = useTranslations("flowCanvas");
  const rf = useReactFlow();
  const byCode = useMemo(() => new Map(resources.map((r) => [r.resource_code, r])), [resources]);
  const steps = useMemo(
    () => flow.steps.map((s) => ({ ...s, station: byCode.get(s.code)?.station_code ?? null })),
    [flow.steps, byCode],
  );
  const arrows: Arrow[] = useMemo(() => {
    const out: Arrow[] = flow.arrows.map((a, i) => ({
      id: `a${i}`,
      from: a.from_step,
      to: a.to_step,
      rework: a.rework,
      jobs: a.jobs,
      share: a.share,
      lessCertain: a.less_certain,
      uncertainJobs: a.uncertain_jobs,
    }));
    // Input and Output arrows for the steps where many jobs start or end; the few others are
    // listed under the canvas, so rare paths do not hide the main ones.
    const many = (n: number) => 100 * n >= IO_MIN_PCT * flow.jobs;
    for (const s of flow.steps) {
      const io = { rework: false, share: null, lessCertain: false, uncertainJobs: 0 };
      if (s.first_jobs && many(s.first_jobs))
        out.push({ id: `in-${s.code}`, from: INPUT, to: s.code, jobs: s.first_jobs, ...io });
      if (s.last_jobs && many(s.last_jobs))
        out.push({ id: `out-${s.code}`, from: s.code, to: OUTPUT, jobs: s.last_jobs, ...io });
    }
    return out;
  }, [flow]);
  const found = useMemo(() => autoLayout(steps, arrows), [steps, arrows]);
  const [positions, setPositions] = useState<Positions>(found);
  const history = useRef<Positions[]>([]);
  const [hover, setHover] = useState<Hover>(null);
  const [motion, setMotion] = useState(() => !reducedMotion());
  const [full, setFull] = useState(false);
  const [canUndo, setCanUndo] = useState(false);
  const dragStart = useRef<Positions | null>(null);

  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setFull(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full]);
  useEffect(() => {
    const id = window.setTimeout(() => void rf.fitView({ padding: 0.1, duration: 0 }), 0);
    return () => window.clearTimeout(id);
  }, [full, found, rf]);

  const remember = useCallback((before: Positions) => {
    history.current = [...history.current.slice(-49), before];
    setCanUndo(true);
  }, []);

  const lit = useMemo(() => {
    if (!hover) return null;
    const ids = new Set<string>();
    const cards = new Set<string>();
    for (const a of arrows) {
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
  }, [hover, arrows]);

  const hoverApi = useMemo(() => ({ setHover, lit }), [lit]);

  const stations = useMemo(() => {
    const groups = new Map<string, string[]>();
    for (const s of steps)
      if (s.station) groups.set(s.station, [...(groups.get(s.station) ?? []), s.code]);
    return [...groups.entries()].map(([code, members]) => ({
      code,
      name: byCode.get(members[0] ?? "")?.station_name ?? code,
      members,
      box: stationBox(members.flatMap((m) => (positions[m] ? [positions[m]] : []))),
    }));
  }, [steps, positions, byCode]);

  const nodes: Node[] = useMemo(() => {
    const out: Node[] = [];
    for (const st of stations) {
      if (!st.box) continue;
      out.push({
        id: `station:${st.code}`,
        type: "station",
        position: { x: st.box.x, y: st.box.y },
        data: { name: st.name, w: st.box.w, h: st.box.h },
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
        ariaLabel:
          data.io === "input"
            ? t("input")
            : data.io === "output"
              ? t("output")
              : t("stepAria", { code: data.code, name: data.name ?? "" }),
      });
    card(INPUT, {
      code: INPUT,
      name: null,
      kind: null,
      jobs: flow.jobs,
      missingFinish: 0,
      io: "input",
    });
    for (const s of steps) {
      const r = byCode.get(s.code);
      card(s.code, {
        code: s.code,
        name: r?.name ?? null,
        kind: r?.kind ?? null,
        jobs: s.jobs,
        missingFinish: s.missing_finish,
        io: null,
      });
    }
    card(OUTPUT, {
      code: OUTPUT,
      name: null,
      kind: null,
      jobs: flow.jobs,
      missingFinish: 0,
      io: "output",
    });
    return out;
  }, [stations, steps, positions, byCode, flow.jobs, t]);

  const routes = useMemo(() => routeArrows(positions, arrows), [positions, arrows]);
  const edges: Edge[] = useMemo(
    () =>
      arrows
        .flatMap((a) => {
          const r = routes[a.id];
          return r ? [{ a, r }] : [];
        })
        .map(({ a, r }) => ({
          id: a.id,
          source: a.from,
          target: a.to,
          type: "route",
          data: {
            arrow: a,
            d: r.d,
            label: r.label,
            motion,
          },
        })),
    [arrows, routes, motion],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setPositions((prev) => {
        let next = prev;
        for (const c of changes) {
          if (c.type !== "position" || !c.position) continue;
          if (dragStart.current === null) dragStart.current = prev;
          if (c.id.startsWith("station:")) {
            const st = stations.find((s) => `station:${s.code}` === c.id);
            if (!st?.box) continue;
            const dx = c.position.x - st.box.x;
            const dy = c.position.y - st.box.y;
            next = { ...next };
            for (const m of st.members) {
              const p = next[m];
              if (p) next[m] = { x: p.x + dx, y: p.y + dy };
            }
          } else {
            next = { ...next, [c.id]: c.position };
          }
          if (c.dragging === false) {
            if (!c.id.startsWith("station:")) next = moveAside(next, c.id);
            if (dragStart.current) remember(dragStart.current);
            dragStart.current = null;
          }
        }
        return next;
      });
    },
    [stations, remember],
  );

  const reorganize = () => {
    remember(positions);
    setPositions(found);
    window.setTimeout(() => void rf.fitView({ padding: 0.1, duration: 150 }), 0);
  };
  const undo = () => {
    const last = history.current.pop();
    if (last) setPositions(last);
    setCanUndo(history.current.length > 0);
  };
  const uncertain = flow.arrows.filter((a) => a.less_certain && !a.rework).length;

  return (
    <div
      className={
        full
          ? "fixed inset-0 z-50 grid grid-rows-[auto_1fr] gap-2 bg-bg p-4"
          : "grid grid-rows-[auto_1fr] gap-2"
      }
      role={full ? "dialog" : undefined}
      aria-modal={full ? true : undefined}
      aria-label={full ? t("fullTitle") : undefined}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
        <span className="text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted">
          {t("strip")}
        </span>
        <div className="flex flex-wrap gap-1">
          <Button aria-pressed={motion} onPress={() => setMotion((m) => !m)}>
            {t("movement")}
          </Button>
          <Button onPress={reorganize}>{t("reorganize")}</Button>
          <Button onPress={undo} isDisabled={!canUndo}>
            {t("undo")}
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
          <Button aria-pressed={full} onPress={() => setFull((f) => !f)}>
            {full ? t("closeFull") : t("full")}
          </Button>
        </div>
      </div>
      <div
        className={`relative rounded-panel border border-line bg-surface ${full ? "" : "h-[520px]"}`}
        data-testid="flow-canvas"
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
        <HoverContext value={hoverApi}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            edgeTypes={EDGE_TYPES}
            onNodesChange={onNodesChange}
            snapToGrid
            snapGrid={[GRID, GRID]}
            nodesConnectable={false}
            edgesFocusable={false}
            minZoom={0.2}
            maxZoom={2}
            fitView
            proOptions={{ hideAttribution: true }}
            ariaLabelConfig={{ "node.a11yDescription.default": t("keyboardHelp") }}
          />
        </HoverContext>
      </div>
      <p className="text-xs text-muted">
        {t("hint")}
        {uncertain > 0 && ` ${t("uncertainSummary", { n: uncertain })}`}
        {flow.other_routes_jobs > 0 && ` ${t("otherRoutes", { n: flow.other_routes_jobs })}`}
      </p>
      <p className="text-xs text-muted">
        <RareEnds flow={flow} />
      </p>
    </div>
  );
}

/** The plant's flow found in the data, as an interactive map (approved mockup, CI0005 seq 06). */
export function FlowCanvas({ flow, resources }: { flow: Flow; resources: Resource[] }) {
  return (
    <ReactFlowProvider>
      {/* A new flow (new data) starts from its own layout. */}
      <Canvas
        key={`${flow.import_id}-${flow.jobs}-${flow.arrows.length}-${resources
          .map((r) => `${r.resource_code}:${r.station_code}`)
          .join(",")}`}
        flow={flow}
        resources={resources}
      />
    </ReactFlowProvider>
  );
}

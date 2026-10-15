import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";
import { ConstraintMarker } from "./ConstraintMarker";
import { formatFigure, type FigureLike } from "./figure";
import { FigureValue } from "./FigureValue";
import { KpiReadout } from "./KpiReadout";
import { LiveDot } from "./LiveDot";
import { MicroLabel } from "./MicroLabel";
import { Panel } from "./Panel";
import { STATE_STYLE, StatusChip, type ResourceState } from "./StatusChip";

const LOSS: FigureLike = {
  value: 4_100_000,
  unit: "eur_cents",
  formula_id: "lost_throughput_v1",
  inputs: { constraint_h_lost: 20, throughput_per_constraint_h_eur_cents: 205_000 },
  confidence: "high",
};

describe("MicroLabel", () => {
  it("renders uppercase, tracked, muted text", () => {
    render(<MicroLabel>Paint line</MicroLabel>);
    const label = screen.getByText("Paint line");
    expect(label.className).toMatch(/uppercase/);
    expect(label.className).toMatch(/text-muted/);
  });
});

describe("Panel", () => {
  it("is a region named by its micro label, with status on the right", () => {
    render(
      <Panel label="PNT-01" status="LIVE 14:32:07 UTC">
        body
      </Panel>,
    );
    const region = screen.getByRole("region", { name: "PNT-01" });
    expect(region).toHaveTextContent("LIVE 14:32:07 UTC");
    expect(region).toHaveTextContent("body");
    expect(region.className).toMatch(/rounded-panel/);
    expect(region.className).not.toMatch(/shadow/);
  });
});

describe("LiveDot", () => {
  it("pulses only when motion is allowed and is hidden from screen readers", () => {
    const { container } = render(<LiveDot />);
    const dot = container.querySelector("[data-live-dot]") as HTMLElement;
    expect(dot.getAttribute("aria-hidden")).toBe("true");
    expect(dot.className).toMatch(/motion-safe:animate-live/);
    expect(dot.className).not.toMatch(/(^| )animate-live/);
  });
});

describe("StatusChip", () => {
  it.each(Object.keys(STATE_STYLE) as ResourceState[])("%s shows glyph and label", (state) => {
    const { container } = render(<StatusChip state={state} />);
    const chip = container.querySelector(`[data-state="${state}"]`) as HTMLElement;
    expect(chip).toHaveTextContent(state.toUpperCase());
    expect(chip).toHaveTextContent(STATE_STYLE[state].glyph);
  });

  it("uses the translated label", () => {
    render(<StatusChip state="starved" label="UITGEHONGERD" />);
    expect(screen.getByText("UITGEHONGERD")).toBeInTheDocument();
  });

  it("never uses the constraint colour", () => {
    for (const style of Object.values(STATE_STYLE)) expect(style.colour).not.toMatch(/constraint/);
  });
});

describe("ConstraintMarker", () => {
  it("draws four corner brackets and the tag", () => {
    const { container } = render(<ConstraintMarker>PNT-01</ConstraintMarker>);
    expect(screen.getByText("CONSTRAINT")).toBeInTheDocument();
    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(4);
    expect(screen.getByText("PNT-01")).toBeInTheDocument();
  });

  it("is the only component that uses the constraint colour", () => {
    const dir = join(process.cwd(), "src/components/");
    const users = readdirSync(dir)
      .filter((f) => f.endsWith(".tsx") && !f.endsWith(".test.tsx"))
      .filter((f) => readFileSync(dir + f, "utf8").includes("constraint"))
      .filter((f) => /(text|border|bg)-constraint/.test(readFileSync(dir + f, "utf8")));
    expect(users).toEqual(["ConstraintMarker.tsx"]);
  });
});

describe("Button", () => {
  it("presses with mouse and keyboard", async () => {
    const onPress = vi.fn();
    render(
      <Button variant="primary" onPress={onPress}>
        Accept
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Accept" });
    await userEvent.click(button);
    button.focus();
    await userEvent.keyboard("{Enter}");
    expect(onPress).toHaveBeenCalledTimes(2);
    expect(button.className).toMatch(/rounded-control/);
  });
});

describe("KpiReadout", () => {
  it("shows the numeral, delta and impact", () => {
    render(<KpiReadout label="Lost throughput" figure={LOSS} delta="+12%" impact="€ / month" />);
    expect(screen.getByText("Lost throughput")).toBeInTheDocument();
    expect(screen.getByText("€41,000")).toBeInTheDocument();
    expect(screen.getByText("+12%")).toBeInTheDocument();
    expect(screen.getByText("€ / month")).toBeInTheDocument();
  });

  it("shows the formula and inputs on keyboard focus", async () => {
    render(<KpiReadout label="Lost" figure={LOSS} formulaText="lost € = hours × rate" />);
    await userEvent.tab();
    const tip = await screen.findByRole("tooltip");
    expect(tip).toHaveTextContent("lost_throughput_v1");
    expect(tip).toHaveTextContent("lost € = hours × rate");
    expect(tip).toHaveTextContent("constraint_h_lost");
    expect(tip).toHaveTextContent("confidence high");
  });

  it("shows Missing with its reason, never a number", async () => {
    const missing: FigureLike = {
      ...LOSS,
      value: { missing: "rate", reason: "no constraint detected yet", confidence_impact: "none" },
      confidence: "none",
    };
    render(<KpiReadout label="Lost" figure={missing} missingLabel="Ontbreekt" />);
    expect(screen.getByText("Ontbreekt")).toBeInTheDocument();
    await userEvent.tab();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("no constraint detected yet");
  });
});

describe("formatFigure", () => {
  it("formats per unit and locale without calculating", () => {
    expect(formatFigure(LOSS, "nl")).toMatch(/^€\s41\.000$/);
    expect(formatFigure({ ...LOSS, value: 20.25, unit: "h" })).toBe("20.3 h");
    expect(formatFigure({ ...LOSS, value: 99.9, unit: "pct" })).toBe("99.9%");
    expect(formatFigure({ ...LOSS, value: 12, unit: "rows" })).toBe("12 rows");
  });
});

describe("FigureValue", () => {
  it("shows the value inline and its formula on keyboard focus", async () => {
    render(
      <FigureValue
        figure={{ ...LOSS, value: 12.5, unit: "min_per_unit", formula_id: "task_time_median_v1" }}
      />,
    );
    expect(screen.getByText("12.5 min/unit")).toBeInTheDocument();
    await userEvent.tab();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("task_time_median_v1");
  });
});

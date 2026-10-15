// @vitest-environment node
// WCAG 2.2 contrast for every text token on --bg and --surface, in both themes.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries(
    [...body.matchAll(/--([a-z-]+):\s*(#[0-9a-f]{6});/g)].map((m) => [m[1], m[2]]),
  );
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT = [
  "text",
  "text-muted",
  "accent",
  "constraint",
  "status-ok",
  "status-warn",
  "status-bad",
];
const GRAPHICS = ["text-faint", "status-idle"];
function tok(tokens: Record<string, string>, name: string): string {
  return tokens[name] ?? "#ffffff";
}

const THEMES = { white: block('[data-theme="white"]'), dark: block('[data-theme="dark"]') };

describe.each(Object.entries(THEMES))("%s theme", (_name, tokens) => {
  it("defines every token", () => {
    for (const token of [...TEXT, ...GRAPHICS, "bg", "surface", "on-accent"]) {
      expect(tokens[token], token).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it.each(["bg", "surface"])("text tokens reach 4.5:1 on --%s", (background) => {
    for (const token of TEXT) {
      const ratio = contrast(tok(tokens, token), tok(tokens, background));
      expect(ratio, `${token} on ${background}: ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(["bg", "surface"])("faint and idle reach 3:1 on --%s", (background) => {
    for (const token of GRAPHICS) {
      const ratio = contrast(tok(tokens, token), tok(tokens, background));
      expect(ratio, `${token} on ${background}: ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(3);
    }
  });

  it("text on the accent reaches 4.5:1", () => {
    expect(contrast(tok(tokens, "on-accent"), tok(tokens, "accent"))).toBeGreaterThanOrEqual(4.5);
  });
});

it("the white theme is the default (:root)", () => {
  expect(css).toMatch(/:root,\s*\[data-theme="white"\]/);
});

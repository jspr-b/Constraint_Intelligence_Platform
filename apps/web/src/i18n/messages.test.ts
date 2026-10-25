import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import en from "../../messages/en.json";
import { TERMS } from "../lib/glossary";
import { GROUPS, PAGE_KEYS, ROLES } from "../lib/pages";

function keys(value: unknown, prefix = ""): string[] {
  if (value === null || typeof value !== "object") return [prefix];
  return Object.entries(value).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k));
}

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return path.endsWith(".tsx") && !path.endsWith(".test.tsx") ? [path] : [];
  });
}

describe("messages", () => {
  it("no message is empty", () => {
    for (const messages of [en]) {
      for (const key of keys(messages)) {
        const value = key
          .split(".")
          .reduce<unknown>((o, k) => (o as Record<string, unknown>)[k], messages);
        expect(String(value).trim(), key).not.toBe("");
      }
    }
  });

  it("every page, group and role has a label", () => {
    for (const page of PAGE_KEYS) expect(en.nav.pages[page], page).toBeTruthy();
    for (const group of GROUPS) expect(en.nav.groups[group.key], group.key).toBeTruthy();
    for (const role of ROLES) expect(en.roles[role], role).toBeTruthy();
  });

  it("components contain no hard-coded UI text", () => {
    const root = join(process.cwd(), "src");
    const offenders = files(root).flatMap((file) =>
      [
        ...readFileSync(file, "utf8").matchAll(/(?<![=-])>\s*([A-Za-z][A-Za-z ,.'!?-]{2,})\s*</g),
      ].map((m) => `${file.replace(root, "src")}: ${m[1]}`),
    );
    expect(offenders).toEqual([]);
  });

  it("every export format's files, tables and fields have a label", () => {
    const mappings = join(process.cwd(), "..", "..", "packages", "connectors", "mappings");
    for (const format of readdirSync(mappings)) {
      const yaml = readFileSync(join(mappings, format, "mapping.yaml"), "utf8");
      const tables = yaml.split(/\n\s*- source: /).slice(1);
      for (const table of tables) {
        const source = (table.split("\n")[0] ?? "").trim();
        const target = /\n\s+target: (\w+)/.exec(table)?.[1] ?? "";
        expect(en.import.source[source as keyof typeof en.import.source], source).toBeTruthy();
        expect(en.model.tables[target as keyof typeof en.model.tables], target).toBeTruthy();
        expect(en.import.unlocks[target as keyof typeof en.import.unlocks], target).toBeTruthy();
        for (const [, field] of table.matchAll(/\n\s{6}(\w+): \{/g))
          expect(en.model.fields[field as keyof typeof en.model.fields], field).toBeTruthy();
      }
    }
  });

  it("every minimum and optional export has a name, and every optional one says what it adds", () => {
    const checklist = readFileSync(
      join(
        process.cwd(),
        "..",
        "..",
        "packages",
        "constraint_engine",
        "src",
        "constraint_engine",
        "quality",
        "checklist.py",
      ),
      "utf8",
    );
    const keysOf = (name: string) =>
      [
        ...(new RegExp(`${name}[^=]*= \\(([\\s\\S]*?)\\n\\)`).exec(checklist)?.[1] ?? "").matchAll(
          /\("(\w+)", \(/g,
        ),
      ].map((m) => m[1] ?? "");
    const minimum = keysOf("MINIMUM_SET");
    const optional = keysOf("OPTIONAL_SET");
    expect(minimum).toEqual(["events", "steps", "shifts"]);
    expect(optional.length).toBeGreaterThan(3);
    for (const key of [...minimum, ...optional]) {
      expect(en.import.minimum[key as keyof typeof en.import.minimum], key).toBeTruthy();
      expect(en.guide.items[key as keyof typeof en.guide.items], key).toBeTruthy();
    }
    for (const key of optional)
      expect(en.import.adds[key as keyof typeof en.import.adds], key).toBeTruthy();
  });

  it("every glossary term has a name and a one-line explanation", () => {
    for (const term of TERMS) {
      expect(en.glossary.terms[term].name, term).toBeTruthy();
      expect(en.glossary.terms[term].text.split(". ").length, term).toBeLessThanOrEqual(2);
    }
  });

  it("tags in messages only name glossary terms", () => {
    const known = new Set<string>(TERMS);
    const unknown = keys(en).flatMap((key) => {
      const value = String(
        key.split(".").reduce<unknown>((o, k) => (o as Record<string, unknown>)[k], en),
      );
      return [...value.matchAll(/<([a-z]+)>/g)]
        .map((m) => m[1] ?? "")
        .filter((tag) => !known.has(tag))
        .map((tag) => `${key}: <${tag}>`);
    });
    expect(unknown).toEqual([]);
  });

  it("client text has no developer words", () => {
    const dev = /(_v\d\b|\bAPI\b|IANA|Keycloak|tenant|formula|code_table|UUID|JSON)/i;
    const offenders = keys(en)
      .filter((key) => !key.startsWith("problems.next"))
      .filter((key) => key !== "figure.formulaId") // shown only under Technical details
      .filter((key) =>
        dev.test(
          String(
            key.split(".").reduce<unknown>((o, k) => (o as Record<string, unknown>)[k], en),
          ).replace(/\{[a-z]+\}/gi, ""), // placeholders are not shown
        ),
      );
    expect(offenders).toEqual([]);
  });
});

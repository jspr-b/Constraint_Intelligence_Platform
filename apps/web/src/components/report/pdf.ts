/**
 * The results report as a PDF, drawn from the same model as the page (see model.ts).
 * Standard PDF fonts only, so the file needs nothing else to open offline.
 */
import { PDFDocument, StandardFonts, rgb, type PDFFont, type PDFPage } from "pdf-lib";
import { lineText, type Report } from "./model";

const A4: [number, number] = [595.28, 841.89];
const MARGIN = 56;
const WIDTH = A4[0] - 2 * MARGIN;
const MUTED = rgb(0.35, 0.38, 0.42);
const TEXT = rgb(0.04, 0.05, 0.06);

/**
 * Characters the standard PDF fonts cannot write, swapped for plain ones. Anything else they
 * cannot write makes the export fail with a message, never a silently wrong file.
 */
const SWAP: Record<string, string> = {
  // narrow no-break space and thin space (Intl number and date formats use them)
  " ": " ",
  " ": " ",
  "→": "to",
  "−": "-",
  "≥": ">=",
  "≤": "<=",
  "≈": "about",
};

const SWAPPABLE = new RegExp(`[${Object.keys(SWAP).join("")}]`, "g");

export function pdfSafe(s: string): string {
  return s.replace(SWAPPABLE, (c) => SWAP[c] ?? c);
}

export interface PdfLabels {
  sources: string;
  sourcesIntro: string;
  formula: string;
  inputs: string;
  period: string;
  confidence: string;
  formulaId: string;
  page: (n: number, total: number) => string;
}

function wrap(text: string, font: PDFFont, size: number, width: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const next = line ? `${line} ${word}` : word;
    if (font.widthOfTextAtSize(next, size) <= width || !line) {
      line = next;
    } else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  return lines;
}

export async function reportPdf(report: Report, labels: PdfLabels): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  doc.setTitle(pdfSafe(`${report.title} - ${report.plant}`));
  doc.setSubject(pdfSafe(report.period));
  doc.setCreator("Constraint Intelligence");
  const regular = await doc.embedFont(StandardFonts.Helvetica);
  const bold = await doc.embedFont(StandardFonts.HelveticaBold);

  let page: PDFPage = doc.addPage(A4);
  let y = A4[1] - MARGIN;
  const write = (
    text: string,
    opts: {
      size?: number;
      font?: PDFFont;
      indent?: number;
      color?: typeof TEXT;
      gap?: number;
    } = {},
  ) => {
    const size = opts.size ?? 10;
    const font = opts.font ?? regular;
    const indent = opts.indent ?? 0;
    for (const part of wrap(pdfSafe(text), font, size, WIDTH - indent)) {
      if (y - size < MARGIN) {
        page = doc.addPage(A4);
        y = A4[1] - MARGIN;
      }
      y -= size * 1.35;
      page.drawText(part, { x: MARGIN + indent, y, size, font, color: opts.color ?? TEXT });
    }
    y -= opts.gap ?? 2;
  };

  write(report.title, { size: 20, font: bold, gap: 6 });
  write(report.plant, { size: 12, font: bold });
  write(report.period, { color: MUTED });
  write(report.made, { color: MUTED, gap: 14 });

  for (const section of report.sections) {
    write(section.heading, { size: 13, font: bold, gap: 4 });
    for (const line of section.lines) write(lineText(line), { indent: 8, gap: 4 });
    y -= 10;
  }

  write(labels.sources, { size: 13, font: bold, gap: 4 });
  write(labels.sourcesIntro, { color: MUTED, gap: 8 });
  for (const s of report.sources) {
    write(`[${s.ref}] ${s.label}: ${s.value}`, { font: bold, gap: 1 });
    if (s.formula) write(`${labels.formula}: ${s.formula}`, { indent: 14, size: 9, gap: 1 });
    if (s.inputs.length) {
      write(`${labels.inputs}: ${s.inputs.join("; ")}`, { indent: 14, size: 9, gap: 1 });
    }
    write(`${labels.period}: ${s.period}. ${labels.confidence}: ${s.confidence}.`, {
      indent: 14,
      size: 9,
      gap: 1,
    });
    write(`${labels.formulaId}: ${s.formulaId}`, { indent: 14, size: 8, color: MUTED, gap: 8 });
  }

  const pages = doc.getPages();
  pages.forEach((p, i) =>
    p.drawText(pdfSafe(labels.page(i + 1, pages.length)), {
      x: MARGIN,
      y: MARGIN / 2,
      size: 8,
      font: regular,
      color: MUTED,
    }),
  );
  return doc.save();
}

"""Text and Markdown rendering of the quality report and checklist."""

from constraint_engine.quality.checklist import ChecklistItem, to_markdown
from constraint_engine.quality.report import QualityReport


def report_lines(report: QualityReport) -> list[str]:
    lines = [
        f"Data quality score: {report.score.value} / 100  ({report.score.formula_id})",
        "",
        "Files:",
    ]
    for f in report.files:
        reasons = ", ".join(f"{k} ×{v}" for k, v in f.reasons.items())
        lines.append(f"  {f.file:<24} {f.rows:>7} rows  {f.rejected:>4} rejected  {reasons}")
        lines += [f"      line {e.line}: {e.reason}" for e in f.examples]
    lines += ["", "Gaps:"] if report.gaps else ["", "Gaps: none"]
    for g in report.gaps:
        lines.append(f"  [{g.confidence_impact.label}] {g.description}  → {g.fix}")
    return lines


def checklist_lines(items: list[ChecklistItem]) -> list[str]:
    lines = ["Data checklist (docs/input-data.md):"]
    for i in items:
        r = i.requirement
        lines.append(f"  {r.number:>2} {r.level:<6} {i.status:<8} {r.data}: {i.detail}")
    return lines


def markdown(report: QualityReport, items: list[ChecklistItem] | None) -> str:
    score = f"Score **{report.score.value} / 100** (`{report.score.formula_id}`)"
    out = [f"# Data quality report\n\n{score}\n"]
    out.append("## Files\n\n| File | Rows | Rejected | Reasons |\n|---|---|---|---|")
    for f in report.files:
        reasons = ", ".join(f"{k} ×{v}" for k, v in f.reasons.items())
        out.append(f"| {f.file} | {f.rows} | {f.rejected} | {reasons} |")
    out.append("\n## Gaps\n\n| Impact | Gap | Fix |\n|---|---|---|")
    out += [f"| {g.confidence_impact.label} | {g.description} | {g.fix} |" for g in report.gaps]
    if items is not None:
        out.append("\n## Data checklist\n\n" + to_markdown(items))
    return "\n".join(out) + "\n"

# ADR-0006: Frontend stack and theme

- **Status:** Proposed
- **Date:** 2026-10-15
- **CLAUDE.md reference:** Tech stack (frontend rows), Styling and design system

## Context

CLAUDE.md asks for a distinct, operator-grade interface without a template look, accessible, bilingual from the start. During the mockup review (2026-10-15) the user tried a white theme with a blue accent and made it the default for the mockup.

## Decision

- **Components:** own library in `packages/ui`, built on React Aria Components (headless, accessible) and styled with Tailwind CSS from design tokens. No shadcn/ui.
- **Data views:** Apache ECharts for heatmaps and large series; D3 where a custom view is needed; React Flow for the plant flow; TanStack Table and TanStack Query.
- **Language:** next-intl with English and Dutch message files; no hard-coded UI strings.
- **Icons:** Lucide outline icons, 1.5 px stroke.
- **Fonts:** self-hosted, with licence files: D-DIN (SIL OFL) for display numerals, Inter for UI text, JetBrains Mono for data.
- **Theme:** **white with blue accent `#1F5FD6` is the default**; the dark mission-control theme from CLAUDE.md is the alternative, switchable per user. In both themes the constraint colour is used only for the constraint, and status is never shown by colour alone.
- **Visual reference:** the mockup at https://claude.ai/artifact/PwEw7wGA9zNQGX9Z1VXDPx. Its layout and copy are the target; its sample numbers are not.

## Consequences

- CLAUDE.md's colour section describes the dark theme; the white theme tokens live in `packages/ui` and should be added to CLAUDE.md once the user confirms the default.
- Every page needs contrast checks in both themes.

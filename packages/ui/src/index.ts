/** Shared UI components and design tokens (packages/ui). Styles: import "@cip/ui/styles.css". */
export const UI_VERSION = "0.0.0";
export { Button, type ButtonProps, type ButtonVariant } from "./components/Button";
export { ConstraintMarker, type ConstraintMarkerProps } from "./components/ConstraintMarker";
export { formatFigure, isMissing, type FigureLike, type MissingValue } from "./components/figure";
export { KpiReadout, type KpiReadoutProps } from "./components/KpiReadout";
export { LiveDot } from "./components/LiveDot";
export { MicroLabel } from "./components/MicroLabel";
export { Panel, type PanelProps } from "./components/Panel";
export {
  STATE_STYLE,
  StatusChip,
  type ResourceState,
  type StatusChipProps,
} from "./components/StatusChip";

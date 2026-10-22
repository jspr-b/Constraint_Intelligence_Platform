/** Per-browser preferences in cookies, so the server renders the right theme and language. */
export const THEME_COOKIE = "cip_theme";
export const VIEW_AS_COOKIE = "cip_view_as";
/** Getting-started guide: "hidden" after Hide, "open" after reopening from the menu. */
export const GUIDE_COOKIE = "cip_guide";
export type Theme = "white" | "dark";

export function isTheme(value: string | undefined): value is Theme {
  return value === "white" || value === "dark";
}

export function setPref(name: string, value: string): void {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; samesite=lax`;
}

/** Switch the theme in place; the cookie makes the server render it on the next request. */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

/** Where to go next for an API error code; the label comes from messages `problems.next.<code>`. */
export const NEXT_STEP: Record<string, string> = {
  sign_in_required: "/login",
  session_expired: "/login",
  no_active_account: "/login",
  plant_not_found: "/setup",
  unknown_plant: "/setup",
  unknown_machine: "/import",
  machine_has_station_login: "/users",
  import_running: "/import",
};

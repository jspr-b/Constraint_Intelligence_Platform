import { execFileSync } from "node:child_process";

/** Reset the fixed synthetic e2e tenant once per run (scripts/e2e_seed.py). */
export default function globalSetup(): void {
  execFileSync("uv", ["run", "python", "../../scripts/e2e_seed.py"], { stdio: "ignore" });
}

import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/dist/**",
      "**/.next/**",
      "**/node_modules/**",
      ".venv/**",
      "**/lib/api/schema.d.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.strict,
);

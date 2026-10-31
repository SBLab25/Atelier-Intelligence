import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import jsxA11y from "eslint-plugin-jsx-a11y";

// Next.js core-web-vitals and TypeScript rules, plus the strict jsx-a11y rule set (Spec 13, OD-137). The jsx-a11y
// plugin is already registered by eslint-config-next, so only its strict rules are added here.
export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["**/*.{ts,tsx,mjs}"],
    rules: {
      ...jsxA11y.flatConfigs.strict.rules,
      "no-console": ["error", { allow: ["info", "warn", "error"] }],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/consistent-type-imports": ["error", { fixStyle: "inline-type-imports" }],
      "react/no-danger": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector: "MemberExpression[object.name='process'][property.name='env'] > Identifier[name=/^NEXT_PUBLIC_/]",
          message: "No NEXT_PUBLIC_ variables: configuration is server-only (OD-133).",
        },
      ],
    },
  },
  globalIgnores([".next/**", "node_modules/**", "playwright-report/**", "test-results/**", "next-env.d.ts",
                 "src/lib/api/schema.ts"]),
]);

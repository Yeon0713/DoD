import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // 목업 함수는 실제 API와 같은 인자를 받아 두고 쓰지 않는다. 이름 앞에 _를 붙인 인자는 괜찮다.
    rules: { "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }] },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;

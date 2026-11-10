import base from "../../eslint.config.mjs";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  ...base,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
];

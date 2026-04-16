import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "./openapi.json",
  output: {
    path: "./src/api/generated",
    postProcess: ["prettier", "eslint"],
  },
  plugins: [
    "@hey-api/client-fetch",
    "@hey-api/typescript",
    "@hey-api/sdk",
    {
      name: "@hey-api/transformers",
      dates: true,
    },
    {
      name: "@tanstack/react-query",
    },
  ],
});

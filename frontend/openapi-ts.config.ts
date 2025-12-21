import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  client: "@hey-api/client-fetch",
  input: "./openapi.json",
  output: {
    path: "./src/api/generated",
    format: "prettier",
    lint: "eslint",
  },
  plugins: [
    "@hey-api/typescript",
    "@hey-api/sdk",
    {
      name: "@hey-api/transformers",
      dates: true,
    },
  ],
});

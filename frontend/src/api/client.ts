import { client } from "./generated/client.gen";

const ACCESS_TOKEN_KEY = "hireflow.access_token";

const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

client.setConfig({
  baseUrl,
  credentials: "include",
});

client.interceptors.request.use((request) => {
  const token = getAccessToken();
  if (token) {
    request.headers.set("Authorization", `Bearer ${token}`);
  }
  return request;
});

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token === null) {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  } else {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
  }
}

export { client };

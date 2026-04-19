import { client } from "./generated/client.gen";
import { refreshToken } from "./generated/sdk.gen";

const ACCESS_TOKEN_KEY = "hireflow.access_token";
const REFRESH_TOKEN_KEY = "hireflow.refresh_token";

export const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8080";

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

// Single-flight refresh: if multiple requests 401 simultaneously, only one
// network refresh is in flight; the rest await the same promise.
let refreshPromise: Promise<string | null> | null = null;

function endpointIsRefreshOrLogin(url: string): boolean {
  return (
    url.includes("/auth/refresh") ||
    url.includes("/auth/login") ||
    url.includes("/auth/register")
  );
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  const { data, error } = await refreshToken({
    body: { refresh_token: refresh },
  });
  if (error || !data) {
    clearTokens();
    return null;
  }
  setAccessToken(data.access_token);
  setRefreshToken(data.refresh_token);
  return data.access_token;
}

client.interceptors.response.use(async (response, request) => {
  if (response.status !== 401) return response;
  if (endpointIsRefreshOrLogin(request.url)) return response;

  refreshPromise ??= refreshAccessToken().finally(() => {
    refreshPromise = null;
  });
  const newAccess = await refreshPromise;
  if (!newAccess) return response;

  const retried = request.clone();
  retried.headers.set("Authorization", `Bearer ${newAccess}`);
  return fetch(retried);
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

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token === null) {
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  } else {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, token);
  }
}

export function clearTokens(): void {
  setAccessToken(null);
  setRefreshToken(null);
}

export { client };

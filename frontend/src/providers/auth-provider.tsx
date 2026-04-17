import * as React from "react";

import {
  forgotPassword as apiForgotPassword,
  login as apiLogin,
  logout as apiLogout,
  readMe,
  register as apiRegister,
  resetPassword as apiResetPassword,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "@/api";
import { extractApiError } from "@/lib/api-errors";
import { AuthError } from "@/providers/auth-errors";
import {
  AuthContext,
  type AuthContextValue,
  type User,
} from "@/providers/auth-context";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      if (!getAccessToken()) {
        setIsLoading(false);
        return;
      }
      const { data, error } = await readMe();
      if (cancelled) return;
      if (error || !data) {
        clearTokens();
        setUser(null);
      } else {
        setUser(data);
      }
      setIsLoading(false);
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = React.useCallback(async (email: string, password: string) => {
    const { data: tokens, error } = await apiLogin({
      body: { email, password },
    });
    if (error || !tokens) {
      throw new AuthError(extractApiError(error).message);
    }
    setAccessToken(tokens.access_token);
    setRefreshToken(tokens.refresh_token);

    const { data: me, error: meError } = await readMe();
    if (meError || !me) {
      clearTokens();
      throw new AuthError("Could not load user profile.");
    }
    setUser(me);
  }, []);

  const register = React.useCallback(
    async (email: string, password: string, fullName: string) => {
      const { error } = await apiRegister({
        body: { email, password, full_name: fullName },
      });
      if (error) {
        throw new AuthError(extractApiError(error).message);
      }
    },
    []
  );

  const logout = React.useCallback(async () => {
    const refresh = getRefreshToken();
    if (refresh) {
      await apiLogout({ body: { refresh_token: refresh } });
    }
    clearTokens();
    setUser(null);
  }, []);

  const forgotPassword = React.useCallback(async (email: string) => {
    const { error } = await apiForgotPassword({ body: { email } });
    if (error) {
      throw new AuthError(extractApiError(error).message);
    }
  }, []);

  const resetPassword = React.useCallback(
    async (token: string, newPassword: string) => {
      const { error } = await apiResetPassword({
        body: { token, new_password: newPassword },
      });
      if (error) {
        throw new AuthError(extractApiError(error).message);
      }
    },
    []
  );

  const value = React.useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      login,
      register,
      logout,
      forgotPassword,
      resetPassword,
    }),
    [user, isLoading, login, register, logout, forgotPassword, resetPassword]
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

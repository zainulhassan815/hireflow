import * as React from "react";

import {
  authForgotPassword,
  authLogin,
  authLogout,
  authReadMe,
  authRegister,
  authResetPassword,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "@/api";
import { AuthError } from "@/providers/auth-errors";
import {
  AuthContext,
  type AuthContextValue,
  type User,
} from "@/providers/auth-context";

function errorMessage(error: unknown, fallback: string): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "detail" in error &&
    typeof (error as { detail: unknown }).detail === "string"
  ) {
    return (error as { detail: string }).detail;
  }
  return fallback;
}

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
      const { data, error } = await authReadMe();
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
    const { data: tokens, error } = await authLogin({
      body: { email, password },
    });
    if (error || !tokens) {
      throw new AuthError(errorMessage(error, "Invalid email or password."));
    }
    setAccessToken(tokens.access_token);
    setRefreshToken(tokens.refresh_token);

    const { data: me, error: meError } = await authReadMe();
    if (meError || !me) {
      clearTokens();
      throw new AuthError("Could not load user profile.");
    }
    setUser(me);
  }, []);

  const register = React.useCallback(
    async (email: string, password: string, fullName: string) => {
      const { error } = await authRegister({
        body: { email, password, full_name: fullName },
      });
      if (error) {
        throw new AuthError(errorMessage(error, "Could not create account."));
      }
    },
    []
  );

  const logout = React.useCallback(async () => {
    const refresh = getRefreshToken();
    if (refresh) {
      await authLogout({ body: { refresh_token: refresh } });
    }
    clearTokens();
    setUser(null);
  }, []);

  const forgotPassword = React.useCallback(async (email: string) => {
    const { error } = await authForgotPassword({ body: { email } });
    if (error) {
      throw new AuthError(errorMessage(error, "Could not send reset link."));
    }
  }, []);

  const resetPassword = React.useCallback(
    async (token: string, newPassword: string) => {
      const { error } = await authResetPassword({
        body: { token, new_password: newPassword },
      });
      if (error) {
        throw new AuthError(
          errorMessage(error, "Invalid or expired reset token.")
        );
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

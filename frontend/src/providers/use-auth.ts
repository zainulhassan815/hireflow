import * as React from "react";

import { AuthContext, type AuthContextValue } from "./auth-context";

export function useAuth(): AuthContextValue {
  const context = React.use(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}

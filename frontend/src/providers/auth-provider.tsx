import * as React from "react";

interface User {
  id: string;
  email: string;
  name: string;
}

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  React.useEffect(() => {
    // TODO: Check for existing session/token
    setIsLoading(false);
  }, []);

  const login = async (_email: string, _password: string) => {
    // TODO: Implement login
    throw new Error("Not implemented");
  };

  const logout = async () => {
    // TODO: Implement logout
    setUser(null);
  };

  return (
    <AuthContext value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext>
  );
}

export function useAuth() {
  const context = React.use(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}

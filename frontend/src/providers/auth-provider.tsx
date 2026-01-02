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
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

const STORAGE_KEY = "auth_user";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  React.useEffect(() => {
    // Check for existing session from localStorage
    const storedUser = localStorage.getItem(STORAGE_KEY);
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        localStorage.removeItem(STORAGE_KEY);
      }
    }
    setIsLoading(false);
  }, []);

  const login = async (email: string, _password: string) => {
    // Mock login - simulates API call
    await new Promise((resolve) => setTimeout(resolve, 500));

    // For demo purposes, accept any email/password
    const mockUser: User = {
      id: crypto.randomUUID(),
      email,
      name: email
        .split("@")[0]
        .replace(/[._]/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase()),
    };

    setUser(mockUser);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(mockUser));
  };

  const register = async (email: string, _password: string, name: string) => {
    // Mock registration - simulates API call
    await new Promise((resolve) => setTimeout(resolve, 500));

    // For demo, just simulate success
    const mockUser: User = {
      id: crypto.randomUUID(),
      email,
      name,
    };

    // Don't auto-login after registration, redirect to login
    console.log("User registered:", mockUser);
  };

  const logout = async () => {
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
  };

  return (
    <AuthContext value={{ user, isLoading, login, register, logout }}>
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

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { message } from "antd";
import { clearAccessToken, fetchMe, getAccessToken, login, register, saveAccessToken, type UserRead } from "../api/client";

type AuthContextValue = {
  user: UserRead | null;
  loading: boolean;
  loginWithPassword: (username: string, password: string) => Promise<void>;
  registerUser: (username: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const boot = async () => {
      if (!getAccessToken()) {
        setLoading(false);
        return;
      }
      try {
        setUser(await fetchMe());
      } catch {
        clearAccessToken();
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    void boot();

    const onUnauthorized = (event: Event) => {
      clearAccessToken();
      setUser(null);
      const detail = (event as CustomEvent<{ message?: string }>).detail;
      message.warning(detail?.message || "Session expired, please log in again.");
    };
    window.addEventListener("dailychewer:unauthorized", onUnauthorized);
    return () => window.removeEventListener("dailychewer:unauthorized", onUnauthorized);
  }, []);

  const loginWithPassword = async (username: string, password: string) => {
    const result = await login({ username, password });
    saveAccessToken(result.access_token);
    setUser(result.user);
  };

  const registerUser = async (username: string, password: string, displayName?: string) => {
    await register({ username, password, display_name: displayName });
    await loginWithPassword(username, password);
  };

  const logout = () => {
    clearAccessToken();
    setUser(null);
  };

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      loginWithPassword,
      registerUser,
      logout,
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return context;
}

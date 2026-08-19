"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

export interface User {
  id: number;
  email: string | null;
  username: string | null;
  plan: "free" | "pro";
  is_admin: boolean;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  register: (email: string, password: string) => Promise<void>;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => void;
  changePassword: (oldPassword: string, newPassword: string) => Promise<void>;
}

const TOKEN_KEY = "tz_token";
const AuthContext = createContext<AuthState | null>(null);

async function authFetch(path: string, body?: unknown, token?: string | null) {
  const res = await fetch(`/api/auth/${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Něco se pokazilo");
  return data;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
    if (!token) {
      setLoading(false);
      return;
    }
    authFetch("me", undefined, token)
      .then((d) => setUser(d.user))
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false));
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const d = await authFetch("register", { email, password });
    localStorage.setItem(TOKEN_KEY, d.token);
    setUser(d.user);
  }, []);

  const login = useCallback(async (identifier: string, password: string) => {
    const d = await authFetch("login", { identifier, password });
    localStorage.setItem(TOKEN_KEY, d.token);
    setUser(d.user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }, []);

  const changePassword = useCallback(async (oldPassword: string, newPassword: string) => {
    const token = localStorage.getItem(TOKEN_KEY);
    await authFetch("change-password", { old_password: oldPassword, new_password: newPassword }, token);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, register, login, logout, changePassword }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

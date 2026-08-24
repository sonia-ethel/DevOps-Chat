// © 2024–2026 TOURE Arnaud Patrick
// Licensed under the MIT License

import { createContext, useContext, useState, useEffect } from "react";
import type { ReactNode } from "react";
import axiosClient from "../api/axiosClient";

interface User {
  id: number;
  email: string;
  is_admin: boolean;
  created_at: string;
}

interface AuthContextType {
  token: string | null;
  user: User | null;
  loading: boolean;
  login: (token: string) => void;
  logout: () => void;
}

//  Pas besoin de FC ici, juste ReactNode pour `children`
const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [token, setToken] = useState<string | null>(() => {
    return localStorage.getItem("access_token");
  });
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchUserInfo = async () => {
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const response = await axiosClient.get("/auth/me");
        setUser(response.data);
      } catch (error) {
        console.error("Failed to fetch user info:", error);
        // Don't call logout here to avoid infinite loop
        localStorage.removeItem("access_token");
        setToken(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    fetchUserInfo();
  }, [token]);

  const login = (newToken: string) => {
    localStorage.setItem("access_token", newToken);
    setToken(newToken);
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ token, user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

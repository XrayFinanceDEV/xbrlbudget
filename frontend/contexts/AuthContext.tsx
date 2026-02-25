"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { setAuthToken } from "@/lib/api";

interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Sync token to API client
  useEffect(() => {
    setAuthToken(token);
  }, [token]);

  useEffect(() => {
    // Listen for JWT from parent iframe via postMessage
    const handleMessage = (event: MessageEvent) => {
      // In production, validate origin:
      // if (event.origin !== 'https://formulafinance.app') return;

      if (event.data?.type === "AUTH_TOKEN" && event.data?.token) {
        setToken(event.data.token);
        setIsLoading(false);
      }

      if (event.data?.type === "AUTH_LOGOUT") {
        setToken(null);
      }
    };

    window.addEventListener("message", handleMessage);

    // Request token from parent (in case we loaded after parent sent it)
    if (window.parent !== window) {
      window.parent.postMessage({ type: "REQUEST_AUTH_TOKEN" }, "*");
    }

    // Dev mode: if no token received within 1s, stop loading
    // Backend will use DEV_USER_ID fallback when no Authorization header
    const devTimeout = setTimeout(() => {
      setIsLoading(false);
    }, 1000);

    return () => {
      window.removeEventListener("message", handleMessage);
      clearTimeout(devTimeout);
    };
  }, []);

  return (
    <AuthContext.Provider
      value={{
        token,
        isAuthenticated: !!token,
        isLoading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}

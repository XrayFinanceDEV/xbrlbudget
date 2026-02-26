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
    const PARENT_ORIGIN = process.env.NEXT_PUBLIC_PARENT_ORIGIN || "";

    // Listen for JWT from parent iframe via postMessage
    const handleMessage = (event: MessageEvent) => {
      // Validate origin in production (skip if not configured)
      if (PARENT_ORIGIN && event.origin !== PARENT_ORIGIN) return;

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
      window.parent.postMessage({ type: "REQUEST_AUTH_TOKEN" }, PARENT_ORIGIN || "*");
    }

    // When NOT in iframe (standalone dev mode): short timeout, backend uses DEV_USER_ID fallback
    // When in iframe: longer timeout to allow postMessage token exchange to complete
    const isInIframe = window.parent !== window;
    const devTimeout = setTimeout(() => {
      setIsLoading(false);
    }, isInIframe ? 5000 : 1000);

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

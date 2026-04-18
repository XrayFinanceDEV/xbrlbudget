"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { setAuthToken } from "@/lib/api";

interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** Logo URL from parent app (postMessage) or JWT user_metadata */
  logoUrl: string | null;
  /** Consulting firm / user display name (Ragione Sociale) from parent or JWT */
  userName: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/** Decode JWT payload without verifying (signature verified server-side) */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);

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

        // Accept logo_url + name from parent postMessage (preferred)
        const parentLogo = event.data.logo_url;
        const parentName = event.data.ragione_sociale ?? event.data.company_name ?? event.data.name;

        const payload = decodeJwtPayload(event.data.token);
        const meta = payload?.user_metadata as Record<string, unknown> | undefined;

        if (typeof parentLogo === "string" && parentLogo) {
          setLogoUrl(parentLogo);
        } else {
          const logo = meta?.logo_url ?? meta?.avatar_url ?? meta?.logo;
          if (typeof logo === "string" && logo) setLogoUrl(logo);
        }

        if (typeof parentName === "string" && parentName) {
          setUserName(parentName);
        } else {
          const name = meta?.ragione_sociale ?? meta?.company_name ?? meta?.full_name ?? meta?.name;
          if (typeof name === "string" && name) setUserName(name);
        }
      }

      if (event.data?.type === "AUTH_LOGOUT") {
        setToken(null);
        setLogoUrl(null);
        setUserName(null);
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
        logoUrl,
        userName,
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

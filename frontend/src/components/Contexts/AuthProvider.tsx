import { ReactNode, createContext, useCallback, useContext, useEffect, useState } from "react";
import axios, { Axios, InternalAxiosRequestConfig } from "axios";
import { toast } from "sonner";
import Cookies from "js-cookie";

export interface AmcatSessionUser {
  loading: boolean;
  email?: string;
  name?: string;
  image?: string;
  authenticated: boolean;
  api: Axios;
}

export interface AmcatSession {
  user: AmcatSessionUser;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

async function createUser(signOut: () => void): Promise<AmcatSessionUser> {
  let sessionCookie = parseClientSessionCookie();

  const api = axios.create({
    baseURL: "/api/",
    withCredentials: true,
  });

  // if sessionCookie is invalid, break the session.
  // This is strict, because the sessioncookie is the only way for the client to know
  // if an amcat session cookie (httponly) is present
  if (sessionCookie === "broken") {
    signOut();
    sessionCookie = null;
  }

  // We use a promise to avoid multiple requests performing the refresh flow
  let refreshQueue: Promise<null> | undefined;

  // Inject csrf token on every request, because server updates it on refresh flow
  api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
    const csrf = Cookies.get("CSRF-TOKEN") || "";
    config.headers["X-CSRF-TOKEN"] = csrf;

    if (sessionCookie) {
      if (!refreshQueue) refreshQueue = refreshToken(csrf);
      try {
        await refreshQueue;
      } catch (e) {
        // if token refresh failed, redirect to login
        signOut();
      }
      refreshQueue = undefined;
    }

    config.headers["X-CSRF-TOKEN"] = Cookies.get("CSRF-TOKEN");
    return config;
  });

  if (sessionCookie) {
    return { loading: false, authenticated: true, email: sessionCookie.email, api };
  } else {
    return { loading: false, authenticated: false, api };
  }
}

async function refreshToken(csrf: string): Promise<null> {
  const session = parseClientSessionCookie();
  if (!session || session === "broken") throw new Error("Session cookie was deleted or broken during session");

  const now = Date.now() / 1000;
  const nearfuture = now + 10; // refresh x seconds before expires
  // if (exp < nearfuture) {
  if (true) {
    await axios.post("/api/auth/refresh", {}, { headers: { "X-CSRF-TOKEN": csrf } });
  }
  return null;
}

const SessionContext = createContext<AmcatSession | null>(null);

export function AuthSessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AmcatSessionUser>({
    loading: true,
    authenticated: false,
    api: axios.create({ baseURL: "/api/" }),
  });

  const signIn = useCallback(async () => {
    const destination = window.location.pathname === "/" ? `${window.location.origin}/projects` : window.location.href;
    const loginUrl = `/api/auth/login?returnTo=${encodeURIComponent(destination)}`;
    window.location.href = loginUrl;
  }, []);

  const signOut = useCallback(async () => {
    try {
      const csrf = Cookies.get("CSRF-TOKEN") || "";
      await axios.post("/api/auth/logout", {}, { headers: { "X-CSRF-TOKEN": csrf } });
      window.location.reload();
    } catch (e) {
      console.log(e);
      toast.error("An error occurred during logout.");
    }
  }, []);

  useEffect(() => {
    createUser(signOut).then((user) => setUser(user));
  }, [signOut]);

  return <SessionContext.Provider value={{ user, signIn, signOut }}>{children}</SessionContext.Provider>;
}

export const useAmcatSession = (): AmcatSession => {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useAmcatSession must be used within an AuthSessionProvider");
  }
  return context;
};

interface ClientSessionCookie {
  exp: number;
  email: string;
}

function parseClientSessionCookie(): ClientSessionCookie | null | "broken" {
  const cookie = Cookies.get("client_session");
  if (!cookie) return null;

  try {
    const json = decodeURIComponent(cookie);
    const { exp, email } = JSON.parse(json);
    return { exp, email };
  } catch (e) {
    return "broken";
  }
}

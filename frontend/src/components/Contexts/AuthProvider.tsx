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

async function createUser(): Promise<AmcatSessionUser> {
  const { email } = parseClientSessionCookie();
  const api = axios.create({
    baseURL: "/api/",
    withCredentials: true,
  });

  // We use a promise to avoid multiple requests performing the refresh flow
  let refreshQueue: Promise<null> | undefined;

  // Inject csrf token on every request, because server updates it on refresh flow
  api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
    const csrf = Cookies.get("CSRF-TOKEN") || "";
    config.headers["X-CSRF-TOKEN"] = csrf;

    if (email) {
      if (!refreshQueue) refreshQueue = refreshToken(csrf);
      await refreshQueue;
      refreshQueue = undefined;
    }

    config.headers["X-CSRF-TOKEN"] = Cookies.get("CSRF-TOKEN");
    return config;
  });

  if (email) {
    return { loading: false, authenticated: true, email, api };
  } else {
    return { loading: false, authenticated: false, api };
  }
}

async function refreshToken(csrf: string): Promise<null> {
  const { exp, email } = parseClientSessionCookie();
  if (!email || !exp) return null;

  const now = Date.now() / 1000;
  const nearfuture = now + 10; // refresh x seconds before expires
  if (exp < nearfuture) {
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

  useEffect(() => {
    createUser().then((user) => setUser(user));
  }, []);

  const signIn = useCallback(async () => {
    const returnTo = encodeURIComponent(window.location.href);
    const loginUrl = `/api/auth/login?returnTo=${returnTo}`;
    window.location.href = loginUrl;
  }, []);

  const signOut = useCallback(async () => {
    if (!user) return;
    try {
      await user.api.post("auth/logout");
      const currentPage = window.location.href;
      window.location.href = currentPage; //refresh
    } catch (e) {
      console.log(e);
      toast.error("An error occurred during logout.");
    }
  }, [user]);

  return <SessionContext.Provider value={{ user, signIn, signOut }}>{children}</SessionContext.Provider>;
}

export const useAmcatSession = (): AmcatSession => {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useAmcatSession must be used within an AuthSessionProvider");
  }
  return context;
};

function parseClientSessionCookie() {
  const cookie = Cookies.get("client_session");
  if (!cookie) return { exp: undefined, email: undefined };

  const parts = cookie.split(".");
  const exp = Number(parts[0]);
  const email = parts.slice(1).join(".");

  return { exp, email };
}

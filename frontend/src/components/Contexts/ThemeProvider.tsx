import { createContext, useContext, useEffect, useState } from "react";

type Mode = "light" | "dark" | "default";

type ThemeProviderState = {
  theme: { mode: Mode };
  setMode: (mode: Mode) => void;
};

const ThemeProviderContext = createContext<ThemeProviderState | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<Mode>(() => (localStorage.getItem("theme-mode") as Mode) || "default");

  useEffect(() => {
    const root = window.document.documentElement;

    root.classList.remove("light", "dark");

    if (mode === "default") {
      const systemTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
      root.classList.add(systemTheme);
    } else {
      root.classList.add(mode);
    }

    localStorage.setItem("theme-mode", mode);
  }, [mode]);

  return <ThemeProviderContext.Provider value={{ theme: { mode }, setMode }}>{children}</ThemeProviderContext.Provider>;
}

export const useTheme = () => {
  const context = useContext(ThemeProviderContext);
  if (context === undefined) throw new Error("useTheme must be used within a ThemeProvider");
  return context;
};

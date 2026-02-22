"use client";

import { Moon, Sun, SunMoon } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { DropdownMenuItem } from "../ui/dropdown-menu";

interface ThemeToggleProps {
  label?: boolean;
}

export default function ThemeToggle({ label }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) return <SunMoon className="mr-3 h-5 w-5" />;

  function renderIcon() {
    // if not on client
    if (typeof window === "undefined") return <SunMoon className="mr-3 h-5 w-5" />;
    if (theme === "dark") return <Sun className="mr-3 h-5 w-5" />;
    return <Moon className="mr-3 h-5 w-5" />;
  }

  return (
    <DropdownMenuItem
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setTheme(theme === "dark" ? "light" : "dark");
      }}
    >
      {renderIcon()}
      {label ? (theme === "dark" ? "Light mode" : "Dark mode") : ""}
    </DropdownMenuItem>
  );
}

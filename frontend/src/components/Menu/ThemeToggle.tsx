import { Moon, Sun, SunMoon } from "lucide-react";
import { useEffect, useState } from "react";
import { DropdownMenuItem } from "../ui/dropdown-menu";
import { useTheme } from "../Contexts/ThemeProvider";

interface ThemeToggleProps {
  label?: boolean;
}

export default function ThemeToggle({ label }: ThemeToggleProps) {
  const { theme, setMode } = useTheme();

  const mode =
    theme.mode === "default"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme.mode;

  function renderIcon() {
    if (mode !== "dark") return <Sun className="mr-3 h-5 w-5" />;
    return <Moon className="mr-3 h-5 w-5" />;
  }

  return (
    <DropdownMenuItem
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setMode(mode === "dark" ? "light" : "dark");
      }}
    >
      {renderIcon()}
      {label ? (mode === "dark" ? "Dark mode" : "Light mode") : ""}
    </DropdownMenuItem>
  );
}

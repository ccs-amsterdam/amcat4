import { ChevronDown, Info } from "lucide-react";
import { ReactNode, useState } from "react";
import { cn } from "@/lib/utils";

interface InfoBoxProps {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  storageKey?: string;
  className?: string;
}

export function InfoBox({ title, children, defaultOpen = true, storageKey, className }: InfoBoxProps) {
  const [open, setOpen] = useState(() => {
    if (storageKey) {
      const stored = localStorage.getItem(storageKey);
      if (stored !== null) return stored === "true";
    }
    return defaultOpen;
  });

  function toggle() {
    const next = !open;
    setOpen(next);
    if (storageKey) localStorage.setItem(storageKey, String(next));
  }

  return (
    <div className={cn("rounded-lg border border-primary/30 bg-muted/20", className)}>
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center gap-2 rounded-lg bg-primary/10 px-4 py-3 text-left font-medium text-primary transition-colors hover:bg-primary/15"
        aria-expanded={open}
      >
        <Info className="h-4 w-4 shrink-0" />
        <span className="flex-1">{title}</span>
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 transition-transform duration-200", open && "rotate-180")}
        />
      </button>
      <div
        className={cn(
          "overflow-hidden transition-all duration-200",
          open ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0",
        )}
      >
        <div className="border-t border-primary/20 px-4 pb-4 pt-3 text-sm text-foreground/85">
          {children}
        </div>
      </div>
    </div>
  );
}

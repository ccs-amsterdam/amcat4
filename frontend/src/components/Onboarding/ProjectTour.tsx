import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "@tanstack/react-router";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import useLocalStorage from "@/lib/useLocalStorage";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { AmcatUserRole } from "@/interfaces";
import { hasMinAmcatRole } from "@/lib/utils";

interface Props {
  projectId: string;
  user: AmcatSessionUser;
  projectRole: AmcatUserRole | undefined;
}

interface StepConfig {
  overlayClassName?: string;
  highlights?: string[];
}

const STEPS: { title: string; description: string; body: React.ReactNode; config?: StepConfig }[] = [
  {
    title: "Your Project Dashboard",
    description: "This is the Dashboard — your main workspace for exploring the project's documents.",
    body: (
      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
        <li>• The search bar at the top filters all views simultaneously</li>
        <li>• Use the tabs below the search bar to switch between views</li>
        <li>• Your query and tab selection are stored in the URL — bookmark or share at any time</li>
      </ul>
    ),
  },
  {
    title: "Summary",
    description: "The Summary view shows a live sample of your documents alongside auto-generated visualizations.",
    body: (
      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
        <li>• <span className="font-medium text-secondary">Highlighted above:</span> the search bar filters by keyword; the filter button adds structured field filters</li>
        <li>• The document list on the left updates with your active query</li>
        <li>• Charts are generated automatically for date, keyword, and number fields</li>
      </ul>
    ),
    config: {
      overlayClassName: "bg-black/15",
      highlights: ["search-input", "filter-button"],
    },
  },
  {
    title: "Aggregate",
    description: "The Aggregate view lets you group and chart your documents across any field.",
    body: (
      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
        <li>• <span className="font-medium text-secondary">Highlighted left:</span> pick a display type (line chart, bar chart, table, or list) and an axis field to group by</li>
        <li>• Add a second axis for cross-tabulation (e.g. multiple lines per category)</li>
        <li>• Combine with the search bar to aggregate only a filtered subset</li>
      </ul>
    ),
    config: {
      overlayClassName: "bg-black/15",
      highlights: ["aggregate-display", "aggregate-axis"],
    },
  },
  {
    title: "Settings",
    description: "Settings shows the project description, owner contact info, and administrative actions.",
    body: (
      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
        <li>• Find the project owner's contact details here if you need help</li>
        <li>• Admins can manage users, configure fields, export data, or archive the project</li>
      </ul>
    ),
  },
];

function TourHighlight({ targets }: { targets: string[] }) {
  const [rects, setRects] = useState<{ top: number; left: number; width: number; height: number }[]>([]);

  useEffect(() => {
    function update() {
      const newRects = targets.flatMap((t) => {
        const el = document.querySelector(`[data-tour="${t}"]`);
        if (!el) return [];
        const r = el.getBoundingClientRect();
        return [{ top: r.top, left: r.left, width: r.width, height: r.height }];
      });
      setRects(newRects);
    }
    update();
    const interval = setInterval(update, 100);
    window.addEventListener("resize", update);
    return () => {
      clearInterval(interval);
      window.removeEventListener("resize", update);
    };
  }, [targets]);

  return createPortal(
    <>
      {rects.map((r, i) => (
        <div
          key={i}
          className="pointer-events-none fixed z-[55] rounded-md ring-[3px] ring-secondary ring-offset-1"
          style={{ top: r.top - 3, left: r.left - 3, width: r.width + 6, height: r.height + 6 }}
        />
      ))}
    </>,
    document.body,
  );
}

export default function ProjectTour({ projectId, user, projectRole }: Props) {
  const storageKey = `project-tour-${user.email ?? "guest"}`;
  const [seen, setSeen] = useLocalStorage<boolean>(storageKey, false);
  const [step, setStep] = useState(0);
  const navigate = useNavigate();

  const open = user.authenticated && !seen && hasMinAmcatRole(projectRole, "METAREADER");

  useEffect(() => {
    if (!open) return;
    setStep(0);
    navigate({ to: "/projects/$project/dashboard", params: { project: projectId }, search: (prev) => ({ ...prev, tab: "summary" }) });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (step === 0 || step === 1) {
      navigate({ to: "/projects/$project/dashboard", params: { project: projectId }, search: (prev) => ({ ...prev, tab: "summary" }) });
    } else if (step === 2) {
      navigate({ to: "/projects/$project/dashboard", params: { project: projectId }, search: (prev) => ({ ...prev, tab: "aggregate" }) });
    } else if (step === 3) {
      navigate({ to: "/projects/$project/settings", params: { project: projectId } });
    }
  }, [step]);

  function dismiss() {
    setSeen(true);
  }

  function finish() {
    setSeen(true);
    navigate({ to: "/projects/$project/dashboard", params: { project: projectId }, search: { tab: "summary" } });
  }

  const isFirst = step === 0;
  const isLast = step === STEPS.length - 1;
  const current = STEPS[step];
  const { overlayClassName, highlights = [] } = current.config ?? {};

  return (
    <>
    {open && highlights.length > 0 && <TourHighlight targets={highlights} />}
    <Dialog open={open} onOpenChange={(o) => { if (!o) dismiss(); }}>
      <DialogContent hideClose overlayClassName={overlayClassName} className="max-w-md">
        <DialogHeader>
          <DialogTitle>{current.title}</DialogTitle>
          <DialogDescription>{current.description}</DialogDescription>
        </DialogHeader>

        {current.body}

        <DialogFooter className="mt-6 flex items-center justify-between gap-2">
          <div className="flex gap-1.5">
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={`h-2 w-2 rounded-full transition-colors ${i === step ? "bg-primary" : "bg-muted"}`}
              />
            ))}
          </div>

          <div className="flex gap-2">
            {!isFirst && (
              <Button variant="outline" size="sm" onClick={() => setStep((s) => s - 1)}>
                Back
              </Button>
            )}
            {isFirst && (
              <Button variant="ghost" size="sm" onClick={dismiss}>
                Skip
              </Button>
            )}
            {!isLast ? (
              <Button size="sm" onClick={() => setStep((s) => s + 1)}>
                Next
              </Button>
            ) : (
              <Button size="sm" onClick={finish}>
                Done
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}

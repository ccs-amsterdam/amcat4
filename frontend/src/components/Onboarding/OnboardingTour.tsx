import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import useLocalStorage from "@/lib/useLocalStorage";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

interface Props {
  user: AmcatSessionUser;
}

const STEPS = [
  {
    title: "Welcome to AmCAT",
    description: "AmCAT is a platform for storing, querying, and annotating large collections of text documents — built for academic research in the social sciences and humanities.",
    body: (
      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
        <li>• Manage thousands to millions of documents in one place</li>
        <li>• Full-text search and structured filtering</li>
        <li>• Aggregations, exports, and a Python/R API</li>
        <li>• Share access with colleagues through fine-grained permissions</li>
      </ul>
    ),
  },
  {
    title: "Projects",
    description: "Everything in AmCAT is organized into projects. A project is a collection of documents that share the same structure (fields).",
    body: (
      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
        <li>• Each project has its own set of documents and fields</li>
        <li>• You can have multiple projects — one per study, dataset, or team</li>
        <li>• Projects can be public, restricted, or completely private</li>
        <li>• Admins can invite collaborators with different roles</li>
      </ul>
    ),
  },
  {
    title: "Search & Query",
    description: "Once a project has data, you have powerful tools to explore it.",
    body: (
      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
        <li>• Full-text search with Boolean operators</li>
        <li>• Filter on any field (date, source, category, …)</li>
        <li>• Aggregate results into charts and tables</li>
        <li>• Export results or query directly from Python or R</li>
      </ul>
    ),
  },
  {
    title: "Get Started",
    description: "You're ready to go. Head to the projects page to create a new project or browse existing ones.",
    body: null,
  },
];

export default function OnboardingTour({ user }: Props) {
  const storageKey = `amcat-onboarding-seen-${user.email ?? "guest"}`;
  const [seen, setSeen] = useLocalStorage<boolean>(storageKey, false);
  const [step, setStep] = useState(0);
  const navigate = useNavigate();

  const open = user.authenticated && !seen;

  useEffect(() => {
    if (open) setStep(0);
  }, [open]);

  function dismiss() {
    setSeen(true);
  }

  function finish() {
    setSeen(true);
    navigate({ to: "/projects" });
  }

  const isFirst = step === 0;
  const isLast = step === STEPS.length - 1;
  const current = STEPS[step];

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) dismiss(); }}>
      <DialogContent hideClose className="max-w-md">
        <DialogHeader>
          <DialogTitle>{current.title}</DialogTitle>
          <DialogDescription>{current.description}</DialogDescription>
        </DialogHeader>

        {current.body}

        <DialogFooter className="mt-6 flex items-center justify-between gap-2">
          {/* Progress dots */}
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
                Go to Projects
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

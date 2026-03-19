import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import useLocalStorage from "@/lib/useLocalStorage";
import { BookOpen, FolderOpen, Search, Sparkles } from "lucide-react";

const WIZARD_KEY = "wizard_seen_v1";

const steps = [
  {
    icon: <Sparkles className="h-12 w-12 text-primary" />,
    title: "Welcome to AmCAT4",
    description:
      "AmCAT4 is an open-source platform for storing, searching, and analyzing large collections of text. It runs on Elasticsearch and is designed for researchers and analysts who need scalable, accessible text analysis.",
  },
  {
    icon: <FolderOpen className="h-12 w-12 text-primary" />,
    title: "Projects",
    description:
      "Projects are containers for document collections. You can create your own project and upload documents to it, or request access to an existing project. Use the Projects page to get started.",
  },
  {
    icon: <BookOpen className="h-12 w-12 text-primary" />,
    title: "Uploading Data",
    description:
      "Upload documents via CSV in the Data tab of any project you have write access to. You can also upload programmatically using the Python (amcat4py) or R (amcat4r) client libraries.",
  },
  {
    icon: <Search className="h-12 w-12 text-primary" />,
    title: "Search & Analysis",
    description:
      "Use the Dashboard to query your documents with filters and keyword search, browse results article by article, and run aggregate analyses such as date trends and value counts.",
  },
];

export default function OnboardingWizard() {
  const [seen, setSeen] = useLocalStorage<boolean>(WIZARD_KEY, false);
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  // Auto-open on first visit
  useEffect(() => {
    if (!seen) setOpen(true);
  }, [seen]);

  // Listen for manual trigger from AccountMenu
  useEffect(() => {
    function handleTrigger() {
      setStep(0);
      setOpen(true);
    }
    window.addEventListener("start-amcat-tour", handleTrigger);
    return () => window.removeEventListener("start-amcat-tour", handleTrigger);
  }, []);

  function dismiss() {
    setSeen(true);
    setOpen(false);
  }

  function next() {
    if (step < steps.length - 1) {
      setStep(step + 1);
    } else {
      dismiss();
    }
  }

  function back() {
    if (step > 0) setStep(step - 1);
  }

  const current = steps[step];
  const isLast = step === steps.length - 1;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) dismiss(); }}>
      <DialogContent hideClose className="sm:max-w-md">
        <DialogHeader>
          <div className="mb-2 flex justify-center">{current.icon}</div>
          <DialogTitle className="text-center text-xl">{current.title}</DialogTitle>
          <p className="text-xs text-center text-muted-foreground">
            {step + 1} / {steps.length}
          </p>
        </DialogHeader>
        <DialogDescription className="text-center text-sm leading-relaxed">
          {current.description}
        </DialogDescription>
        <DialogFooter className="flex-row items-center justify-between gap-2 sm:justify-between">
          <Button variant="ghost" size="sm" onClick={dismiss}>
            Skip
          </Button>
          <div className="flex gap-2">
            {step > 0 && (
              <Button variant="outline" size="sm" onClick={back}>
                ← Back
              </Button>
            )}
            <Button size="sm" onClick={next}>
              {isLast ? "Get started" : "Next →"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

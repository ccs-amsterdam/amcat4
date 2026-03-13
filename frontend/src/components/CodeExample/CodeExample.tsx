import { AmcatProjectId, AmcatQuery } from "@/interfaces";
import { useFields } from "@/api/fields";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Code, Check, Clipboard } from "lucide-react";
import { toast } from "sonner";
import { AuthInfo, CodeAction, generatePython, generateR } from "./codeGenerators";
import { useAmcatConfig } from "@/api/config";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import r from "react-syntax-highlighter/dist/esm/languages/prism/r";
import { oneLight, oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("r", r);

type CodeExampleProps =
  | { action: "search"; projectId: AmcatProjectId; query: AmcatQuery };
// Future: | { action: "aggregate"; projectId: AmcatProjectId; query: AmcatQuery; options: AggregationOptions }

type Language = "python" | "r";

function useDarkMode() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    const observer = new MutationObserver(() => setDark(document.documentElement.classList.contains("dark")));
    observer.observe(document.documentElement, { attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return dark;
}

export default function CodeExample(props: CodeExampleProps) {
  const [open, setOpen] = useState(false);
  const [language, setLanguage] = useState<Language>("python");
  const [includeInstall, setIncludeInstall] = useState(true);
  const [includeConnect, setIncludeConnect] = useState(true);
  const [copied, setCopied] = useState(false);
  const dark = useDarkMode();

  const { data: config } = useAmcatConfig();
  const { user } = useAmcatSession();
  const { data: fieldData } = useFields(user, props.projectId);
  const serverUrl = window.location.origin + "/api";

  const auth: AuthInfo | undefined =
    config?.authorization !== "no_auth" && user.authenticated && user.email
      ? { needsAuth: true, email: user.email, apiKeysUrl: window.location.origin + "/api_keys" }
      : undefined;

  const fields = fieldData?.map((f) => f.name);

  const codeAction: CodeAction = (() => {
    if (props.action === "search") {
      return { action: "search", params: { serverUrl, projectId: props.projectId, query: props.query, fields, auth } };
    }
    // exhaustive — future actions handled here
    throw new Error("Unknown action");
  })();

  const code = language === "python"
    ? generatePython(codeAction, includeInstall, includeConnect)
    : generateR(codeAction, includeInstall, includeConnect);

  function copyToClipboard() {
    navigator.clipboard.writeText(code);
    toast.success("Code copied to clipboard");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} className="gap-1.5">
        <Code className="h-3.5 w-3.5" />
        Show code
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-none">
          <DialogHeader>
            <DialogTitle>Code example</DialogTitle>
          </DialogHeader>

          <div className="flex items-center justify-between gap-4">
            {/* Language toggle */}
            <div className="flex gap-1 rounded-md border p-1">
              {(["python", "r"] as Language[]).map((lang) => (
                <button
                  key={lang}
                  onClick={() => setLanguage(lang)}
                  className={`rounded px-3 py-1 text-sm font-medium transition-colors ${
                    language === lang
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {lang === "python" ? "Python" : "R"}
                </button>
              ))}
            </div>

            <div className="flex gap-4">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={includeConnect}
                  onChange={(e) => setIncludeConnect(e.target.checked)}
                  className="h-4 w-4"
                />
                Include connecting
              </label>
              <label className={`flex cursor-pointer items-center gap-2 text-sm ${!includeConnect ? "opacity-40 pointer-events-none" : ""}`}>
                <input
                  type="checkbox"
                  checked={includeInstall && includeConnect}
                  onChange={(e) => setIncludeInstall(e.target.checked)}
                  disabled={!includeConnect}
                  className="h-4 w-4"
                />
                Include installation
              </label>
            </div>
          </div>

          {/* Code block */}
          <div className="relative">
            <SyntaxHighlighter
              language={language}
              style={dark ? oneDark : oneLight}
              customStyle={{
                margin: 0,
                borderRadius: "0.375rem",
                fontSize: "0.8rem",
                lineHeight: "1.6",
                height: "18rem",
                width: "540px",
                maxWidth: "85vw",
              }}
            >
              {code}
            </SyntaxHighlighter>
            <Button
              variant="ghost"
              size="icon"
              onClick={copyToClipboard}
              className="absolute right-2 top-2 h-7 w-7 opacity-70 hover:opacity-100"
              title="Copy to clipboard"
            >
              {copied ? <Check className="h-4 w-4" /> : <Clipboard className="h-4 w-4" />}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

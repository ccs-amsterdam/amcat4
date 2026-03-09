import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useHasGlobalRole } from "@/api/userDetails";
import { useNavigate } from "@tanstack/react-router";
import { Upload, Loader } from "lucide-react";
import { useRef, useState } from "react";

const CHUNK_SIZE = 5000;

async function* readLines(file: File): AsyncGenerator<string> {
  const stream = file.name.endsWith(".gz")
    ? file.stream().pipeThrough(new DecompressionStream("gzip"))
    : file.stream();
  const reader = stream.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      if (buffer.trim()) yield buffer;
      break;
    }
    buffer += value;
    const lines = buffer.split("\n");
    buffer = lines.pop()!;
    for (const line of lines) if (line.trim()) yield line;
  }
}

export function ImportProject() {
  const { user } = useAmcatSession();
  const canCreate = useHasGlobalRole(user, "WRITER");
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [overrideId, setOverrideId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [docsSent, setDocsSent] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  if (!canCreate) return null;

  function reset() {
    setFile(null);
    setOverrideId("");
    setError(null);
    setDocsSent(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function onImport(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !user) return;
    setLoading(true);
    setError(null);
    setDocsSent(null);

    let projectId: string | null = null;

    try {
      const settings: Record<string, unknown> = {};
      const fields: Record<string, unknown> = {};
      const roles: unknown[] = [];
      let batch: Record<string, unknown>[] = [];
      let totalSent = 0;

      for await (const line of readLines(file)) {
        const obj = JSON.parse(line) as Record<string, unknown>;
        const type = obj._type;
        delete obj._type;

        if (type === "settings") Object.assign(settings, obj);
        else if (type === "field") {
          const name = obj.name as string;
          delete obj.name;
          fields[name] = obj;
        } else if (type === "user_role") {
          roles.push(obj);
        } else if (type === "document") {
          if (!projectId) {
            const metaResult = await user.api.post("/index/import/metadata", {
              settings,
              fields,
              roles,
              override_id: overrideId || null,
            });
            projectId = metaResult.data.project_id as string;
            setDocsSent(0);
          }
          batch.push(obj);
          if (batch.length >= CHUNK_SIZE) {
            await user.api.post(`/index/${projectId}/import/documents`, { documents: batch });
            totalSent += batch.length;
            setDocsSent(totalSent);
            batch = [];
          }
        }
      }

      // Project with no documents
      if (!projectId) {
        const metaResult = await user.api.post("/index/import/metadata", {
          settings,
          fields,
          roles,
          override_id: overrideId || null,
        });
        projectId = metaResult.data.project_id as string;
      }

      // Remaining documents
      if (batch.length > 0) {
        await user.api.post(`/index/${projectId}/import/documents`, { documents: batch });
        totalSent += batch.length;
        setDocsSent(totalSent);
      }

      setOpen(false);
      reset();
      navigate({ to: `/projects/${projectId}/dashboard` });
    } catch (e: any) {
      if (projectId) {
        try { await user.api.delete(`/index/${projectId}`); } catch {}
      }
      setError(e?.response?.data?.detail || "Import failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" className="flex gap-2">
          <Upload className="h-4 w-4" />
          Import project
        </Button>
      </DialogTrigger>
      <DialogContent aria-describedby={undefined} className="w-[500px] max-w-[95vw]">
        <DialogHeader>
          <DialogTitle>Import project</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={onImport}>
          <div className="flex flex-col gap-1">
            <label htmlFor="import-file">Project file (.ndjson or .ndjson.gz)</label>
            <Input
              id="import-file"
              ref={fileRef}
              type="file"
              accept=".ndjson,.gz,.ndjson.gz"
              className="font-extralight file:mr-3 file:text-foreground"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="import-override-id">Override project ID (optional)</label>
            <Input
              id="import-override-id"
              value={overrideId}
              onChange={(e) => setOverrideId(e.target.value)}
              placeholder="Leave empty to use ID from file"
              autoComplete="off"
            />
          </div>
          {loading && (
            <div className="flex flex-col gap-1">
              <div className="text-sm text-muted-foreground text-center">
                {docsSent === null
                  ? "Creating project…"
                  : `Uploading documents: ${docsSent.toLocaleString()} uploaded`}
              </div>
              <Progress value={null} className="animate-pulse" />
            </div>
          )}
          {error && <div className="text-center text-sm text-destructive">{error}</div>}
          <Button type="submit" disabled={!file || loading} className="w-full">
            {loading ? <Loader className="mr-2 h-4 w-4 animate-spin" /> : null}
            Import project
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

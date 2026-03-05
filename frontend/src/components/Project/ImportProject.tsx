import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useHasGlobalRole } from "@/api/userDetails";
import { useNavigate } from "@tanstack/react-router";
import { Upload, Loader } from "lucide-react";
import { useRef, useState } from "react";

export function ImportProject() {
  const { user } = useAmcatSession();
  const canCreate = useHasGlobalRole(user, "WRITER");
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [overrideId, setOverrideId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  if (!canCreate) return null;

  function reset() {
    setFile(null);
    setOverrideId("");
    setError(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function onImport(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !user) return;
    setLoading(true);
    setError(null);
    const formData = new FormData();
    formData.append("file", file);
    const url = `/index/import${overrideId ? `?override_id=${encodeURIComponent(overrideId)}` : ""}`;
    try {
      const result = await user.api.post(url, formData);
      setOpen(false);
      reset();
      navigate({ to: `/projects/${result.data.project_id}/dashboard` });
    } catch (e: any) {
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
          {error && <div className="text-center text-destructive text-sm">{error}</div>}
          <Button type="submit" disabled={!file || loading} className="w-full">
            {loading ? <Loader className="mr-2 h-4 w-4 animate-spin" /> : null}
            Import project
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

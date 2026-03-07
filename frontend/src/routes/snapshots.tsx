import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/snapshots")({
  component: Snapshots,
});

import {
  SnapshotInfo,
  SnapshotRepository,
  useCreateSnapshot,
  useMutateRepositories,
  useSnapshotPathRepo,
  useSnapshotRepositories,
  useSnapshots,
} from "@/api/snapshots";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ui/confirm";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loading } from "@/components/ui/loading";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DatabaseBackup, ExternalLink, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function repoLocation(repo: SnapshotRepository): string {
  const s = repo.settings as Record<string, string>;
  if (repo.type === "fs") return s.location ?? "";
  if (repo.type === "s3") return s.bucket ? `s3://${s.bucket}${s.base_path ? `/${s.base_path}` : ""}` : "";
  if (repo.type === "url") return s.url ?? "";
  return "";
}

function Snapshots() {
  const { user } = useAmcatSession();
  const { data: repositories, isLoading } = useSnapshotRepositories(user);
  const mutate = useMutateRepositories(user);
  const { activate, confirmDialog } = useConfirm();
  const [selectedRepo, setSelectedRepo] = useState<string | undefined>(undefined);

  if (isLoading) return <Loading />;

  const currentRepo = selectedRepo ?? repositories?.[0]?.name;
  const currentRepoInfo = repositories?.find((r) => r.name === currentRepo);

  function handleDelete(repo: SnapshotRepository) {
    activate(
      () =>
        mutate.mutateAsync({ action: "delete", name: repo.name }).then(() => {
          toast.success(`Repository '${repo.name}' unregistered`);
          setSelectedRepo(undefined);
        }),
      {
        description: `Unregister repository '${repo.name}'? This does not delete existing snapshots.`,
        confirmText: "Unregister",
      },
    );
  }

  return (
    <div className="mx-auto mt-12 w-full max-w-5xl px-6 py-6">
      {confirmDialog}
      <div className="mb-6 flex items-center gap-3">
        <DatabaseBackup className="h-6 w-6" />
        <h1 className="text-2xl font-bold">Snapshots</h1>
        <div className="ml-auto">
          <RegisterRepositoryDialog />
        </div>
      </div>

      <HelpText />

      {!repositories || repositories.length === 0 ? (
        <NoRepositoriesMessage />
      ) : (
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Repository</Label>
            <Select value={currentRepo} onValueChange={setSelectedRepo}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Select a repository…" />
              </SelectTrigger>
              <SelectContent>
                {repositories.map((r) => (
                  <SelectItem key={r.name} value={r.name}>
                    {r.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {currentRepoInfo && (
            <>
              <div className="rounded border bg-muted/30 px-4 py-3 text-sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div>
                      <span className="text-muted-foreground">Repository type: </span>
                      <span className="font-medium">{currentRepoInfo.type}</span>
                    </div>
                    {repoLocation(currentRepoInfo) && (
                      <div>
                        <span className="text-muted-foreground">Location: </span>
                        <span className="font-mono">{repoLocation(currentRepoInfo)}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <CreateSnapshotDialog repository={currentRepoInfo.name} />
                    <Button variant="outline" size="sm" onClick={() => handleDelete(currentRepoInfo)}>
                      <Trash2 className="mr-1 h-3.5 w-3.5" />
                      Unregister
                    </Button>
                  </div>
                </div>
              </div>
              <SnapshotTable repository={currentRepoInfo.name} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

function HelpText() {
  return (
    <div className="mb-6 rounded border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
      <p className="mb-1">
        <strong>Snapshots</strong> are incremental backups of all Elasticsearch indices. A{" "}
        <strong>repository</strong> is a storage location (filesystem path or S3 bucket) where
        snapshots are kept. Restoring snapshots is done directly in Elasticsearch, not through this UI.
      </p>
      <a
        href="https://www.elastic.co/guide/en/elasticsearch/reference/current/snapshot-restore.html"
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 text-primary hover:underline"
      >
        Elasticsearch snapshot &amp; restore docs <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}

function NoRepositoriesMessage() {
  return (
    <div className="rounded border border-dashed p-8 text-center text-muted-foreground">
      <DatabaseBackup className="mx-auto mb-3 h-10 w-10 opacity-40" />
      <p className="mb-1 font-medium">No snapshot repositories configured</p>
      <p className="text-sm">
        First ensure <code>path.repo</code> is set in your Elasticsearch config, then register a repository using the
        button above.
      </p>
    </div>
  );
}


function SnapshotTable({ repository }: { repository: string }) {
  const { user } = useAmcatSession();
  const { data: snapshots, isLoading } = useSnapshots(user, repository);

  if (isLoading) return <Loading />;
  if (!snapshots || snapshots.length === 0)
    return <p className="text-sm text-muted-foreground">No snapshots in this repository yet.</p>;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>State</TableHead>
          <TableHead>Indices</TableHead>
          <TableHead>Size</TableHead>
          <TableHead>Started</TableHead>
          <TableHead>Finished</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {snapshots.map((snap) => (
          <SnapshotRow key={snap.uuid} snap={snap} />
        ))}
      </TableBody>
    </Table>
  );
}

function SnapshotRow({ snap }: { snap: SnapshotInfo }) {
  const stateVariant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    SUCCESS: "default",
    IN_PROGRESS: "secondary",
    FAILED: "destructive",
    PARTIAL: "outline",
  };

  return (
    <TableRow>
      <TableCell className="font-mono text-sm">{snap.snapshot}</TableCell>
      <TableCell>
        <Badge variant={stateVariant[snap.state] ?? "outline"}>{snap.state}</Badge>
      </TableCell>
      <TableCell>{snap.indices.length}</TableCell>
      <TableCell className="text-sm">{snap.size_in_bytes != null ? formatBytes(snap.size_in_bytes) : "—"}</TableCell>
      <TableCell className="text-sm">{snap.start_time ? new Date(snap.start_time).toLocaleString() : "—"}</TableCell>
      <TableCell className="text-sm">{snap.end_time ? new Date(snap.end_time).toLocaleString() : "—"}</TableCell>
    </TableRow>
  );
}

function CreateSnapshotDialog({ repository }: { repository: string }) {
  const { user } = useAmcatSession();
  const create = useCreateSnapshot(user);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(() => `snapshot-${new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-")}`);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name) return;
    await create.mutateAsync({ repository, snapshot: name });
    toast.success("Snapshot started");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="mr-1 h-3.5 w-3.5" />
          Create Snapshot
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Snapshot</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label>Snapshot name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Starting…" : "Create"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type RepoType = "fs" | "s3" | "url";

function RegisterRepositoryDialog() {
  const { user } = useAmcatSession();
  const mutate = useMutateRepositories(user);
  const { data: pathRepo } = useSnapshotPathRepo(user);
  const [open, setOpen] = useState(false);
  const [repoName, setRepoName] = useState("");
  const [repoType, setRepoType] = useState<RepoType>("fs");
  // fs fields
  const [fsBase, setFsBase] = useState<string>("");
  const [fsSubdir, setFsSubdir] = useState("");
  // s3 fields
  const [bucket, setBucket] = useState("");
  const [region, setRegion] = useState("");
  const [basePath, setBasePath] = useState("");
  // url fields
  const [url, setUrl] = useState("");

  const effectiveFsBase = fsBase || pathRepo?.[0] || "";
  const fsLocation = fsSubdir ? `${effectiveFsBase}/${fsSubdir}` : effectiveFsBase;

  function buildSettings(): Record<string, string> {
    if (repoType === "fs") return { location: fsLocation };
    if (repoType === "s3") {
      const s: Record<string, string> = { bucket, region };
      if (basePath) s.base_path = basePath;
      return s;
    }
    return { url };
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    await mutate.mutateAsync({ action: "create", name: repoName, type: repoType, settings: buildSettings() });
    toast.success(`Repository '${repoName}' registered`);
    setOpen(false);
    setRepoName("");
    setFsBase("");
    setFsSubdir("");
    setBucket("");
    setRegion("");
    setBasePath("");
    setUrl("");
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">Register Repository</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Register Snapshot Repository</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label>Repository name</Label>
            <Input value={repoName} onChange={(e) => setRepoName(e.target.value)} required placeholder="my-backups" />
          </div>
          <div className="space-y-1">
            <Label>Type</Label>
            <Select value={repoType} onValueChange={(v) => setRepoType(v as RepoType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fs">Filesystem (fs)</SelectItem>
                <SelectItem value="s3">S3</SelectItem>
                <SelectItem value="url">URL (read-only)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {repoType === "fs" && (
            <>
              {pathRepo && pathRepo.length === 0 ? (
                <p className="rounded border border-amber-400 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200">
                  No <code>path.repo</code> is configured in Elasticsearch. Add it to <code>elasticsearch.yml</code>{" "}
                  before registering a filesystem repository.
                </p>
              ) : (
                <>
                  <div className="space-y-1">
                    <Label>Base path</Label>
                    <Select value={effectiveFsBase} onValueChange={setFsBase}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(pathRepo ?? []).map((p) => (
                          <SelectItem key={p} value={p}>
                            {p}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">Configured <code>path.repo</code> values in Elasticsearch.</p>
                  </div>
                  <div className="space-y-1">
                    <Label>Subdirectory (optional)</Label>
                    <Input value={fsSubdir} onChange={(e) => setFsSubdir(e.target.value)} placeholder="my-backups" />
                    {effectiveFsBase && (
                      <p className="font-mono text-xs text-muted-foreground">Location: {fsLocation}</p>
                    )}
                  </div>
                </>
              )}
            </>
          )}
          {repoType === "s3" && (
            <>
              <div className="space-y-1">
                <Label>Bucket</Label>
                <Input value={bucket} onChange={(e) => setBucket(e.target.value)} required placeholder="my-bucket" />
              </div>
              <div className="space-y-1">
                <Label>Region</Label>
                <Input value={region} onChange={(e) => setRegion(e.target.value)} required placeholder="us-east-1" />
              </div>
              <div className="space-y-1">
                <Label>Base path (optional)</Label>
                <Input value={basePath} onChange={(e) => setBasePath(e.target.value)} placeholder="snapshots/" />
              </div>
            </>
          )}
          {repoType === "url" && (
            <div className="space-y-1">
              <Label>URL</Label>
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
                placeholder="https://example.com/snapshots"
              />
            </div>
          )}
          <Button type="submit" disabled={mutate.isPending}>
            {mutate.isPending ? "Registering…" : "Register"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

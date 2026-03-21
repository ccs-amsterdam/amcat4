import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/snapshots")({
  component: Snapshots,
});

import {
  SLMPolicy,
  SnapshotInfo,
  SnapshotRepository,
  useCreateSnapshot,
  useDeleteSnapshot,
  useMutateRepositories,
  useMutateSLMPolicy,
  useSLMPolicies,
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
import { CalendarClock, DatabaseBackup, ExternalLink, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { InfoBox } from "@/components/ui/info-box";
import { useState } from "react";
import { toast } from "sonner";

function shortIso(s: string): string {
  return s.slice(0, 16);
}

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

          {currentRepo && <SLMPoliciesSection repositories={repositories} repository={currentRepo} />}

          {currentRepoInfo && (
            <>
              <div className="flex items-center gap-2 pt-2">
                <DatabaseBackup className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-base font-semibold">Snapshots</h2>
                <div className="ml-auto flex gap-2">
                  <CreateSnapshotDialog repository={currentRepoInfo.name} />
                  <Button variant="outline" size="sm" onClick={() => handleDelete(currentRepoInfo)}>
                    <Trash2 className="mr-1 h-3.5 w-3.5" />
                    Unregister
                  </Button>
                </div>
              </div>
              <div className="rounded border bg-muted/30 px-4 py-2 text-sm">
                <span className="text-muted-foreground">Type: </span>
                <span className="font-medium">{currentRepoInfo.type}</span>
                {repoLocation(currentRepoInfo) && (
                  <>
                    <span className="mx-2 text-muted-foreground">·</span>
                    <span className="text-muted-foreground">Location: </span>
                    <span className="font-mono">{repoLocation(currentRepoInfo)}</span>
                    <span className="ml-1 text-xs text-muted-foreground">(path on the Elasticsearch server or Docker container)</span>
                  </>
                )}
              </div>
              <SnapshotTable repository={currentRepoInfo.name} />
            </>
          )}
        </div>
      )}
      <InfoBox title="Information on snapshots" storageKey="infobox:snapshots" className="mt-6">
        <div className="flex flex-col gap-2 text-sm">
          <p>
            <strong>Snapshots</strong> are incremental backups of all Elasticsearch indices — each snapshot
            stores only what has changed since the previous one, so they are space-efficient. A{" "}
            <strong>repository</strong> is a storage location (filesystem path or S3 bucket) where snapshots
            are kept. <strong>Snapshot policies</strong> automate this on a schedule and manage retention.
            Restoring snapshots is done directly in Elasticsearch, not through this UI.
          </p>
          <p>
            <strong>Important:</strong> the presence of snapshots in this list does not guarantee that your
            data is safe. The server administrator is responsible for ensuring that the snapshot repository
            (e.g. the filesystem directory or S3 bucket) is itself stored or copied to a safe, off-site
            location. It is also strongly recommended to periodically perform recovery tests to verify that
            snapshots can actually be restored successfully.
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
      </InfoBox>
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
  const deleteSnap = useDeleteSnapshot(user);
  const { activate, confirmDialog } = useConfirm();

  if (isLoading) return <Loading />;
  if (!snapshots || snapshots.length === 0)
    return <p className="text-sm text-muted-foreground">No snapshots in this repository yet.</p>;

  function handleDelete(snap: SnapshotInfo) {
    activate(
      () => deleteSnap.mutateAsync({ repository, snapshot: snap.snapshot }).then(() => toast.success(`Snapshot '${snap.snapshot}' deleted`)),
      { description: `Delete snapshot '${snap.snapshot}'? This cannot be undone.`, confirmText: "Delete" },
    );
  }

  const sorted = [...snapshots].sort((a, b) => b.start_time.localeCompare(a.start_time));

  return (
    <>
      {confirmDialog}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>State</TableHead>
            <TableHead>Indices</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Started</TableHead>
            <TableHead>Finished</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((snap) => (
            <SnapshotRow key={snap.uuid} snap={snap} onDelete={handleDelete} />
          ))}
        </TableBody>
      </Table>
    </>
  );
}

function SnapshotRow({ snap, onDelete }: { snap: SnapshotInfo; onDelete: (snap: SnapshotInfo) => void }) {
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
      <TableCell className="text-sm" title={snap.start_time || undefined}>{snap.start_time ? shortIso(snap.start_time) : "—"}</TableCell>
      <TableCell className="text-sm" title={snap.end_time || undefined}>{snap.end_time ? shortIso(snap.end_time) : "—"}</TableCell>
      <TableCell>
        <Button variant="ghost" size="sm" title="Delete snapshot" onClick={() => onDelete(snap)}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </TableCell>
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

const FREQUENCY_OPTIONS = [
  { label: "Hourly", value: "hourly", cron: "0 0 * * * ?" },
  { label: "Daily", value: "daily", cron: "0 0 1 * * ?" },
  { label: "Weekly (Mon)", value: "weekly", cron: "0 0 1 ? * MON" },
  { label: "Monthly", value: "monthly", cron: "0 0 1 1 * ?" },
] as const;

function cronToLabel(cron: string): string {
  return FREQUENCY_OPTIONS.find((f) => f.cron === cron)?.label ?? cron;
}

function SLMPoliciesSection({ repositories, repository }: { repositories: SnapshotRepository[]; repository: string }) {
  const { user } = useAmcatSession();
  const { data: allPolicies, isLoading } = useSLMPolicies(user);
  const policies = allPolicies?.filter((p) => p.repository === repository);
  const mutate = useMutateSLMPolicy(user);
  const { activate, confirmDialog } = useConfirm();

  function handleDelete(policy: SLMPolicy) {
    activate(
      () =>
        mutate.mutateAsync({ action: "delete", policy_id: policy.policy_id }).then(() => {
          toast.success(`Policy '${policy.policy_id}' deleted`);
        }),
      {
        description: `Delete policy '${policy.policy_id}'? Snapshots already taken will not be removed.`,
        confirmText: "Delete",
      },
    );
  }

  function handleExecute(policy: SLMPolicy) {
    mutate.mutateAsync({ action: "execute", policy_id: policy.policy_id }).then(() => {
      toast.success(`Policy '${policy.policy_id}' executed — snapshot starting`);
    });
  }

  return (
    <div className="space-y-3 pt-2">
      {confirmDialog}
      <div className="flex items-center gap-2">
        <CalendarClock className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-base font-semibold">Snapshot Policies</h2>
        <div className="ml-auto">
          <SLMPolicyDialog
            repositories={repositories}
            repository={repository}
            trigger={
              <Button variant="outline" size="sm">
                <Plus className="mr-1 h-3.5 w-3.5" />
                Add Policy
              </Button>
            }
          />
        </div>
      </div>
      {isLoading ? null : !policies || policies.length === 0 ? (
        <p className="text-sm text-muted-foreground">No snapshot policies configured.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Policy ID</TableHead>
              <TableHead>Frequency</TableHead>
              <TableHead>Retain</TableHead>
              <TableHead>Last run</TableHead>
              <TableHead>Next run</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {policies.map((policy) => {
              const lastRun = policy.last_success && policy.last_failure
                ? (policy.last_success > policy.last_failure ? { ts: policy.last_success, ok: true } : { ts: policy.last_failure, ok: false })
                : policy.last_success ? { ts: policy.last_success, ok: true }
                : policy.last_failure ? { ts: policy.last_failure, ok: false }
                : null;
              const initFrequency = FREQUENCY_OPTIONS.find((f) => f.cron === policy.schedule)?.value ?? "daily";
              return (
                <TableRow key={policy.policy_id}>
                  <TableCell className="font-mono text-sm">{policy.policy_id}</TableCell>
                  <TableCell>{cronToLabel(policy.schedule)}</TableCell>
                  <TableCell>{policy.max_count}</TableCell>
                  <TableCell className="text-sm">
                    {lastRun ? (
                      <span className={lastRun.ok ? "text-green-600" : "text-red-600"}>
                        {lastRun.ok ? "✓" : "✗"} {lastRun.ts}
                      </span>
                    ) : "—"}
                  </TableCell>
                  <TableCell className="text-sm">{policy.next_execution ?? "—"}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" title="Run now" onClick={() => handleExecute(policy)}>
                        <Play className="h-3.5 w-3.5" />
                      </Button>
                      <SLMPolicyDialog
                        repositories={repositories}
                        repository={repository}
                        initial={{ policy_id: policy.policy_id, frequency: initFrequency, max_count: policy.max_count }}
                        trigger={
                          <Button variant="ghost" size="sm" title="Edit policy">
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        }
                      />
                      <Button variant="ghost" size="sm" title="Delete policy" onClick={() => handleDelete(policy)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

type FrequencyValue = (typeof FREQUENCY_OPTIONS)[number]["value"];

function SLMPolicyDialog({
  repositories,
  repository: defaultRepository,
  initial,
  trigger,
}: {
  repositories: SnapshotRepository[];
  repository: string;
  initial?: { policy_id: string; frequency: FrequencyValue; max_count: number };
  trigger: React.ReactNode;
}) {
  const { user } = useAmcatSession();
  const mutate = useMutateSLMPolicy(user);
  const [open, setOpen] = useState(false);
  const [policyId, setPolicyId] = useState(initial?.policy_id ?? "");
  const [repository, setRepository] = useState(defaultRepository);
  const [frequency, setFrequency] = useState<FrequencyValue>(initial?.frequency ?? "daily");
  const [maxCount, setMaxCount] = useState(initial?.max_count ?? 7);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const isEdit = !!initial;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    const cron = FREQUENCY_OPTIONS.find((f) => f.value === frequency)!.cron;
    try {
      await mutate.mutateAsync({ action: "create", policy_id: policyId, repository, schedule: cron, max_count: maxCount });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSubmitError(detail ?? "Failed to save policy");
      return;
    }
    toast.success(`Policy '${policyId}' ${isEdit ? "updated" : "created"}`);
    setOpen(false);
    if (!isEdit) setPolicyId("");
    setSubmitError(null);
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setSubmitError(null); }}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Snapshot Policy" : "Create Snapshot Policy"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label>Policy ID</Label>
            <Input
              value={policyId}
              onChange={(e) => setPolicyId(e.target.value)}
              required
              placeholder="daily-backup"
              disabled={isEdit}
            />
          </div>
          <div className="space-y-1">
            <Label>Repository</Label>
            <Select value={repository} onValueChange={setRepository} disabled={isEdit}>
              <SelectTrigger>
                <SelectValue />
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
          <div className="space-y-1">
            <Label>Frequency</Label>
            <Select value={frequency} onValueChange={(v) => setFrequency(v as FrequencyValue)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FREQUENCY_OPTIONS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>
                    {f.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Retain last N snapshots</Label>
            <Input
              type="number"
              min={1}
              max={100}
              value={maxCount}
              onChange={(e) => setMaxCount(Number(e.target.value))}
              required
            />
          </div>
          {submitError && (
            <p className="rounded border border-red-400 bg-red-50 px-3 py-2 text-xs text-red-800 dark:bg-red-950 dark:text-red-200">
              {submitError}
            </p>
          )}
          <Button type="submit" disabled={mutate.isPending}>
            {mutate.isPending ? "Saving…" : isEdit ? "Save" : "Create Policy"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type RepoType = "fs" | "s3" | "url";

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

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
  const [subdirTouched, setSubdirTouched] = useState(false);
  // s3 fields
  const [bucket, setBucket] = useState("");
  const [region, setRegion] = useState("");
  const [basePath, setBasePath] = useState("");
  // url fields
  const [url, setUrl] = useState("");

  const effectiveFsBase = fsBase || pathRepo?.[0] || "";
  const fsLocation = fsSubdir ? `${effectiveFsBase}/${fsSubdir}` : effectiveFsBase;

  function handleRepoNameChange(name: string) {
    setRepoName(name);
    if (!subdirTouched) setFsSubdir(slugify(name));
  }

  function handleFsSubdirChange(value: string) {
    setSubdirTouched(true);
    setFsSubdir(value);
  }

  function buildSettings(): Record<string, string> {
    if (repoType === "fs") return { location: fsLocation };
    if (repoType === "s3") {
      const s: Record<string, string> = { bucket, region };
      if (basePath) s.base_path = basePath;
      return s;
    }
    return { url };
  }

  const [submitError, setSubmitError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    try {
      await mutate.mutateAsync({ action: "create", name: repoName, type: repoType, settings: buildSettings() });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSubmitError(detail ?? "Failed to register repository");
      return;
    }
    toast.success(`Repository '${repoName}' registered`);
    setOpen(false);
    setRepoName("");
    setFsBase("");
    setFsSubdir("");
    setSubdirTouched(false);
    setBucket("");
    setRegion("");
    setBasePath("");
    setUrl("");
    setSubmitError(null);
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setSubmitError(null); setSubdirTouched(false); } }}>
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
            <Input value={repoName} onChange={(e) => handleRepoNameChange(e.target.value)} required placeholder="my-backups" />
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
                    <Input value={fsSubdir} onChange={(e) => handleFsSubdirChange(e.target.value)} placeholder="my-backups" />
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
          {submitError && (
            <p className="rounded border border-red-400 bg-red-50 px-3 py-2 text-xs text-red-800 dark:bg-red-950 dark:text-red-200">
              {submitError}
            </p>
          )}
          <Button type="submit" disabled={mutate.isPending}>
            {mutate.isPending ? "Registering…" : "Register"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

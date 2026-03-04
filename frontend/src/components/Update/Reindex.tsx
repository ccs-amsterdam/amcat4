import { useCount } from "@/api/aggregate";
import { useCreateProject } from "@/api/project";
import { useAmcatProjects } from "@/api/projects";
import { FieldReindexOptions, postReindex } from "@/api/query";
import { useHasGlobalRole } from "@/api/userDetails";
import { useFields } from "@/api/fields";
import { AmcatField, AmcatProject, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { DialogDescription, DialogTitle } from "@radix-ui/react-dialog";
import {
  ArrowRight,
  BarChart,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Lock,
} from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useState, useMemo } from "react";
import { Button } from "../ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "../ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Input } from "../ui/input";
import { DynamicIcon } from "../ui/dynamic-icon";
import { CreateFieldSelectType } from "../Fields/CreateField";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
}

type DestMode = "existing" | "new";
type FieldAction = "new" | "existing" | "exclude";

interface FieldConfig {
  action?: FieldAction;
  targetName?: string;
  type?: string;
}

function getDefaultAction(
  fieldName: string,
  destFields: AmcatField[] | undefined,
  destMode: DestMode,
): FieldAction {
  if (destMode === "new") return "new";
  if (!destFields) return "new";
  return destFields.some((f) => f.name === fieldName) ? "existing" : "new";
}

export default function Reindex({ user, projectId, query }: Props) {
  const { count } = useCount(user, projectId, query);
  const { data: projects } = useAmcatProjects(user);
  const { data: sourceFields } = useFields(user, projectId);
  const canCreateProject = useHasGlobalRole(user, "WRITER");

  const [destMode, setDestMode] = useState<DestMode>("existing");
  const [existingProject, setExistingProject] = useState<AmcatProject | undefined>();
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [newProjectId, setNewProjectId] = useState("");
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectNameEdited, setNewProjectNameEdited] = useState(false);
  const [fieldConfigs, setFieldConfigs] = useState<Record<string, FieldConfig>>({});
  const [fieldConfigOpen, setFieldConfigOpen] = useState(false);
  const [taskResult, setTaskResult] = useState<string | null>(null);
  const [submittedProjectId, setSubmittedProjectId] = useState<string | undefined>();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { mutateAsync: createProjectAsync } = useCreateProject(user);
  const { data: destFields } = useFields(user, destMode === "existing" ? existingProject?.id : undefined);

  // Validate new project ID
  const existingIds = useMemo(() => new Set(projects?.map((p) => p.id) ?? []), [projects]);
  const newProjectIdError = useMemo(() => {
    if (!newProjectId) return "Project ID is required";
    if (/[ .\\]/.test(newProjectId)) return "ID cannot contain spaces, dots, or backslashes";
    if (existingIds.has(newProjectId)) return "A project with this ID already exists";
    return null;
  }, [newProjectId, existingIds]);

  const destinationId = destMode === "existing" ? existingProject?.id : newProjectId;
  const canSubmit =
    !submitting &&
    (destMode === "existing" ? existingProject != null : newProjectId !== "" && newProjectIdError === null);

  function updateFieldConfig(fieldName: string, update: Partial<FieldConfig>) {
    setFieldConfigs((prev) => {
      const existing = prev[fieldName] ?? {};
      const next = { ...existing, ...update };
      if (update.action !== undefined && update.action !== existing.action) delete next.targetName;
      return { ...prev, [fieldName]: next };
    });
  }

  const configuredCount =
    sourceFields?.filter((field) => {
      const c = fieldConfigs[field.name];
      return c && (c.action !== undefined || c.targetName !== undefined || c.type !== undefined);
    }).length ?? 0;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || !destinationId) return;
    setSubmitError(null);
    setSubmitting(true);
    try {
      if (destMode === "new") {
        await createProjectAsync({ id: newProjectId, name: newProjectName });
      }
      // Build field_options — only send non-default entries
      const field_options: Record<string, FieldReindexOptions> = {};
      for (const field of sourceFields ?? []) {
        const config = fieldConfigs[field.name] ?? {};
        const action = config.action ?? getDefaultAction(field.name, destFields, destMode);
        if (action === "exclude") {
          field_options[field.name] = { exclude: true };
        } else {
          const opts: FieldReindexOptions = {};
          if (config.targetName && config.targetName !== field.name) opts.rename = config.targetName;
          if (action === "new" && config.type) opts.type = config.type;
          if (Object.keys(opts).length > 0) field_options[field.name] = opts;
        }
      }
      const res = await postReindex(user, projectId, destinationId, query, field_options);
      setSubmittedProjectId(destinationId);
      setTaskResult(res?.data.task);
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? err?.message ?? "An error occurred";
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  if (count == null) return null;

  return (
    <div className="flex flex-col gap-6">
      <CopyOperationDialog
        open={taskResult != null}
        onOpenChange={() => setTaskResult(null)}
        newProjectId={submittedProjectId}
        taskResultId={taskResult ?? undefined}
      />

      <h4>
        Copy <b className="text-primary">{count}</b> documents
      </h4>

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {/* Destination */}
        <div className="flex flex-col gap-2">
          <div className="flex gap-4 text-sm font-medium">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="destMode"
                value="existing"
                checked={destMode === "existing"}
                onChange={() => { setDestMode("existing"); setFieldConfigs({}); }}
              />
              Existing project
            </label>
            {canCreateProject && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="destMode"
                  value="new"
                  checked={destMode === "new"}
                  onChange={() => { setDestMode("new"); setFieldConfigs({}); }}
                />
                New project
              </label>
            )}
          </div>

          {destMode === "existing" && (
            <div className="flex items-center gap-3">
              <Popover open={newProjectOpen} onOpenChange={setNewProjectOpen}>
                <PopoverTrigger asChild>
                  <Button className="min-w-64 justify-between gap-3" variant="outline">
                    {existingProject?.name ?? "Select destination project"}
                    <ChevronDown className="h-5 w-5" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="start" className="w-72 p-0">
                  <Command>
                    <CommandInput placeholder="Filter projects" autoFocus className="h-9" />
                    <CommandList>
                      <CommandEmpty>No project found</CommandEmpty>
                      <CommandGroup>
                        {projects
                          ?.sort((a, b) => projectLabel(a).localeCompare(projectLabel(b)))
                          .filter((ix) => !user.authenticated || ix.user_role === "WRITER" || ix.user_role === "ADMIN")
                          .filter((ix) => !ix.archived)
                          .filter((ix) => ix.id !== projectId)
                          .map((ix) => (
                            <CommandItem
                              key={ix.id}
                              value={projectLabel(ix)}
                              onSelect={() => {
                                setExistingProject(ix);
                                setNewProjectOpen(false);
                              }}
                            >
                              <span>{projectLabel(ix).replace(/^\//, "")}</span>
                            </CommandItem>
                          ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
          )}

          {destMode === "new" && (
            <div className="flex flex-col gap-2">
              <div className="flex items-start gap-3">
                <div className="flex flex-col gap-1">
                  <Input
                    placeholder="project-id (required)"
                    value={newProjectId}
                    onChange={(e) => {
                      const id = e.target.value.replace(/ /g, "-");
                      setNewProjectId(id);
                      if (!newProjectNameEdited) setNewProjectName(id);
                    }}
                    className="w-56"
                  />
                  {newProjectId && newProjectIdError && (
                    <span className="text-xs text-destructive">{newProjectIdError}</span>
                  )}
                </div>
                <Input
                  placeholder="Display name (optional)"
                  value={newProjectName}
                  onChange={(e) => {
                    setNewProjectName(e.target.value);
                    setNewProjectNameEdited(true);
                  }}
                  className="w-56"
                />
              </div>
            </div>
          )}
        </div>

        {/* Field configuration (expandable) */}
        {sourceFields && sourceFields.length > 0 && (
          <div className="border rounded">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium"
              onClick={() => setFieldConfigOpen((v) => !v)}
            >
              {fieldConfigOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              Configure fields
              {configuredCount > 0 && (
                <span className="ml-1 rounded bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">
                  {configuredCount} configured
                </span>
              )}
            </button>
            {fieldConfigOpen && (
              <FieldConfigTable
                sourceFields={sourceFields}
                fieldConfigs={fieldConfigs}
                onUpdate={updateFieldConfig}
                destFields={destFields}
                destMode={destMode}
              />
            )}
          </div>
        )}

        {submitError && <p className="text-sm text-destructive">{submitError}</p>}

        <div>
          <Button type="submit" disabled={!canSubmit}>
            {submitting ? "Copying…" : "Copy"}
          </Button>
        </div>
      </form>

      <div className="border-primary-100 mt-3 border bg-primary/10 p-2 text-sm">
        <em>Note:</em> Fields in the source project that don't exist in the target project will be copied automatically.
        Expand "Configure fields" to rename, retype, or exclude individual fields.
      </div>
    </div>
  );
}

function projectLabel(ix: AmcatProject) {
  return `${ix.folder || ""}/${ix.name}`;
}

// --- Field config table ---

interface FieldConfigTableProps {
  sourceFields: AmcatField[];
  fieldConfigs: Record<string, FieldConfig>;
  onUpdate: (fieldName: string, update: Partial<FieldConfig>) => void;
  destFields: AmcatField[] | undefined;
  destMode: DestMode;
}

function FieldConfigTable({ sourceFields, fieldConfigs, onUpdate, destFields, destMode }: FieldConfigTableProps) {
  return (
    <div className="border-t text-sm">
      <div className="grid grid-cols-[1fr_8rem_1fr_9rem] gap-x-3 border-b bg-muted/50 px-3 py-1.5 text-xs font-medium text-muted-foreground">
        <span>Source field</span>
        <span>Action</span>
        <span>Target field</span>
        <span>Type</span>
      </div>
      {sourceFields.map((field) => (
        <FieldConfigRow
          key={field.name}
          field={field}
          config={fieldConfigs[field.name] ?? {}}
          onUpdate={onUpdate}
          destFields={destFields}
          destMode={destMode}
        />
      ))}
    </div>
  );
}

function FieldConfigRow({
  field,
  config,
  onUpdate,
  destFields,
  destMode,
}: {
  field: AmcatField;
  config: FieldConfig;
  onUpdate: (fieldName: string, update: Partial<FieldConfig>) => void;
  destFields: AmcatField[] | undefined;
  destMode: DestMode;
}) {
  const defaultAction = getDefaultAction(field.name, destFields, destMode);
  const action = config.action ?? defaultAction;
  const effectiveTargetName = config.targetName ?? field.name;
  const currentType = config.type ?? field.type;
  const destFieldType =
    action === "existing"
      ? (destFields?.find((f) => f.name === effectiveTargetName)?.type ?? field.type)
      : null;

  return (
    <div
      className={`grid grid-cols-[1fr_8rem_1fr_9rem] items-center gap-x-3 border-b px-3 py-1.5 ${action === "exclude" ? "opacity-40" : ""}`}
    >
      {/* Source field */}
      <div className="flex items-center gap-1.5 font-mono text-xs">
        <DynamicIcon type={field.type} className="h-3.5 w-3.5 shrink-0" />
        {field.name}
      </div>

      {/* Action */}
      <select
        value={action}
        onChange={(e) => onUpdate(field.name, { action: e.target.value as FieldAction })}
        className="h-7 rounded border border-input bg-background px-2 text-xs"
      >
        {destMode === "existing" && <option value="existing">Existing field</option>}
        <option value="new">New field</option>
        <option value="exclude">Exclude</option>
      </select>

      {/* Target field */}
      {action === "existing" ? (
        <select
          value={effectiveTargetName}
          onChange={(e) => onUpdate(field.name, { targetName: e.target.value })}
          className="h-7 rounded border border-input bg-background px-2 text-xs"
        >
          {destFields?.map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
      ) : action === "new" ? (
        <Input
          className="h-7 text-xs"
          placeholder={field.name}
          value={config.targetName ?? ""}
          onChange={(e) => onUpdate(field.name, { targetName: e.target.value || undefined })}
        />
      ) : (
        <span className="text-xs text-muted-foreground">—</span>
      )}

      {/* Type */}
      {action === "new" ? (
        <CreateFieldSelectType
          type={currentType as any}
          setType={(t) => onUpdate(field.name, { type: t })}
        />
      ) : action === "existing" ? (
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Lock className="h-3 w-3" />
          {destFieldType}
        </span>
      ) : (
        <span />
      )}
    </div>
  );
}

// --- Post-submit dialog ---

interface CopyOperationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  newProjectId?: string;
  taskResultId?: string;
}

function CopyOperationDialog({ open, onOpenChange, newProjectId, taskResultId }: CopyOperationDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <CheckCircle className="h-6 w-6 text-green-500" />
            Copy Operation Started
          </DialogTitle>
          <DialogDescription>
            Your copy operation has been initiated successfully. Choose an option below to proceed.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4 py-4">
          <Button asChild variant="outline" className="justify-between">
            <Link to="/projects/$project/dashboard" params={{ project: newProjectId! }}>
              View Destination Project
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" className="justify-between">
            <Link to="/task/$task" params={{ task: taskResultId! }}>
              View Copy Progress
              <BarChart className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Close and Return to Source Project</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

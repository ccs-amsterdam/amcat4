import { createFileRoute, useNavigate } from "@tanstack/react-router";

export const Route = createFileRoute("/projects/$project/settings")({
  component: SettingsPage,
});

import { useArchiveProject, useDeleteProject, useMutateProject, useProject, useUploadProjectImage } from "@/api/project";
import { useAmcatProjects } from "@/api/projects";
import { ContactInfo } from "@/components/Project/ContactInfo";
import { Button } from "@/components/ui/button";
import { ErrorMsg } from "@/components/ui/error-message";
import { Form } from "@/components/ui/form";
import { JSONForm } from "@/components/ui/jsonForm";
import { Loading } from "@/components/ui/loading";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { AmcatProject } from "@/interfaces";
import { amcatProjectUpdateSchema, contactInfoSchema } from "@/schemas";
import { zodResolver } from "@hookform/resolvers/zod";
import { Download, FolderArchive, ImagePlus, Pencil, Trash2, X, Check, FolderInput } from "lucide-react";
import { AmcatSessionUser, useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useConfirm } from "@/components/ui/confirm";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

function SettingsPage() {
  const { project: projectParam } = Route.useParams();
  const { user } = useAmcatSession();
  const projectId = decodeURI(projectParam);
  const { data: project, isLoading: loadingProject } = useProject(user, projectId);

  if (loadingProject) return <Loading />;
  if (!project) return <ErrorMsg type="Not Allowed">Need to be logged in</ErrorMsg>;

  const isAdmin = project.user_role === "ADMIN";

  return (
    <div className="flex w-full  flex-col">
      <div className={` ${isAdmin ? "" : "hidden"}`}>
        <div className="flex gap-2">
          <ExportProject project={project} />
          <ArchiveProject project={project} />
          <DeleteProject project={project} />
        </div>
      </div>
      <Settings user={user} project={project} isAdmin={isAdmin} />
    </div>
  );
}

function Settings({ user, project, isAdmin }: { user: AmcatSessionUser; project: AmcatProject; isAdmin: boolean }) {
  const { mutateAsync } = useMutateProject(user);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleValue, setTitleValue] = useState(project.name);
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionValue, setDescriptionValue] = useState(project.description || "");
  const [imageModalOpen, setImageModalOpen] = useState(false);

  function saveTitle() {
    mutateAsync({ id: project.id, name: titleValue }).then(() => setEditingTitle(false));
  }

  function saveDescription() {
    mutateAsync({ id: project.id, description: descriptionValue }).then(() => setEditingDescription(false));
  }

  return (
    <div className="grid grid-cols-1 items-start justify-between gap-6 p-3">
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          {editingTitle ? (
            <div className="flex items-center gap-2">
              <Input
                className="text-2xl font-bold h-auto py-1"
                value={titleValue}
                onChange={(e) => setTitleValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveTitle();
                  if (e.key === "Escape") { setTitleValue(project.name); setEditingTitle(false); }
                }}
                autoFocus
              />
              <Button size="icon" variant="ghost" onClick={saveTitle}><Check className="h-4 w-4" /></Button>
              <Button size="icon" variant="ghost" onClick={() => { setTitleValue(project.name); setEditingTitle(false); }}><X className="h-4 w-4" /></Button>
            </div>
          ) : (
            <div className="flex items-center gap-2 group">
              <h2 className="text-2xl font-bold">{project.name}</h2>
              {isAdmin && (
                <button onClick={() => setEditingTitle(true)} className="opacity-0 group-hover:opacity-100 transition-opacity">
                  <Pencil className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                </button>
              )}
            </div>
          )}
        </div>

        {editingDescription ? (
          <div className="flex flex-col gap-2">
            <Textarea
              value={descriptionValue}
              onChange={(e) => setDescriptionValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") { setDescriptionValue(project.description || ""); setEditingDescription(false); }
              }}
              autoFocus
              rows={3}
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={saveDescription}><Check className="h-3 w-3 mr-1" />Save</Button>
              <Button size="sm" variant="ghost" onClick={() => { setDescriptionValue(project.description || ""); setEditingDescription(false); }}><X className="h-3 w-3 mr-1" />Cancel</Button>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-2 group">
            <p className="text-base text-muted-foreground">
              {project.description || <i className="text-sm">(No description)</i>}
            </p>
            {isAdmin && (
              <button onClick={() => setEditingDescription(true)} className="mt-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                <Pencil className="h-4 w-4 text-muted-foreground hover:text-foreground" />
              </button>
            )}
          </div>
        )}
      </div>

      <FolderSelector project={project} user={user} isAdmin={isAdmin} />

      {isAdmin ? (
        <>
          <button
            onClick={() => setImageModalOpen(true)}
            className="group relative w-max rounded focus:outline-none"
          >
            {project.image_url ? (
              <div className="relative">
                <img
                  src={project.image_url}
                  alt="Project image"
                  className="max-w-[300px] rounded object-contain"
                />
                <div className="absolute inset-0 flex items-center justify-center rounded bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
                  <Pencil className="h-8 w-8 text-white" />
                </div>
              </div>
            ) : (
              <div className="flex h-32 w-48 flex-col items-center justify-center gap-2 rounded border-2 border-dashed border-muted-foreground/30 text-muted-foreground transition-colors hover:border-muted-foreground/60 hover:text-foreground">
                <ImagePlus className="h-8 w-8" />
                <span className="text-sm">Add project image</span>
              </div>
            )}
          </button>
          <ImageUploadModal
            open={imageModalOpen}
            onOpenChange={setImageModalOpen}
            project={project}
            user={user}
          />
        </>
      ) : project.image_url ? (
        <img
          src={project.image_url}
          alt="Project image"
          className="max-w-[300px] rounded object-contain"
        />
      ) : null}

      <div>
        <div className="group prose w-max max-w-full rounded-md bg-primary/10 px-6 py-2 dark:prose-invert">
          <div className="flex items-center gap-2">
            <h4 className="text-foreground/60">Contact information</h4>
            {isAdmin && <EditContactButton project={project} user={user} className="opacity-0 group-hover:opacity-100 transition-opacity" />}
          </div>
          <ContactInfo contact={project.contact} />
        </div>
      </div>
      <div className={`${project.archived ? "" : "hidden"}`}>
        <p className="w-max max-w-full rounded border border-destructive p-2 text-destructive">
          This project was archived on {project.archived?.split(".")[0]}
        </p>
      </div>
      <div className="grid grid-cols-[auto,1fr] gap-x-6 text-sm text-muted-foreground">
        <div>Project ID</div>
        <div>{project.id}</div>
        <div>Size</div>
        <div>{formatSimpleBytes(project.bytes || null)}</div>
      </div>
    </div>
  );
}

function EditContactButton({ project, user, className }: { project: AmcatProject; user: AmcatSessionUser; className?: string }) {
  const { mutateAsync } = useMutateProject(user);
  const [open, setOpen] = useState(false);
  const form = useForm<z.input<typeof amcatProjectUpdateSchema>>({
    resolver: zodResolver(amcatProjectUpdateSchema),
    defaultValues: { ...project, archive: undefined },
  });

  function onSubmit(values: z.input<typeof amcatProjectUpdateSchema>) {
    mutateAsync(amcatProjectUpdateSchema.parse(values)).then(() => setOpen(false));
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <button onClick={() => setOpen(true)} className={`not-prose text-muted-foreground hover:text-foreground ${className ?? ""}`}>
        <Pencil className="h-4 w-4" />
      </button>
      <DialogContent className="w-[500px] max-w-[90vw]">
        <DialogHeader>
          <DialogTitle>Edit contact information</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-3">
            <JSONForm control={form.control} name="contact" label="Contact information" schema={contactInfoSchema} />
            <Button type="submit">Save</Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

function FolderSelector({
  project,
  user,
  isAdmin,
}: {
  project: AmcatProject;
  user: AmcatSessionUser;
  isAdmin: boolean;
}) {
  const { mutateAsync } = useMutateProject(user);
  const { data: allProjects } = useAmcatProjects(user);
  const [open, setOpen] = useState(false);
  const [newFolder, setNewFolder] = useState("");

  const existingFolders = [...new Set(
    (allProjects ?? [])
      .map((p) => p.folder)
      .filter((f): f is string => !!f && f !== project.folder),
  )].sort();

  function moveTo(folder: string) {
    const normalized = folder.replace(/\/+/g, "/").replace(/^\/|\/$/g, "");
    mutateAsync({ id: project.id, folder: normalized }).then(() => setOpen(false));
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="font-bold">Folder</span>
      <span className="text-primary">{project.folder || <i className="text-muted-foreground">(none)</i>}</span>
      {isAdmin && (
        <Dialog open={open} onOpenChange={(o) => { setOpen(o); setNewFolder(""); }}>
          <button onClick={() => setOpen(true)} className="text-muted-foreground hover:text-foreground">
            <FolderInput className="h-4 w-4" />
          </button>
          <DialogContent className="w-[360px] max-w-[90vw]">
            <DialogHeader>
              <DialogTitle>Move to folder</DialogTitle>
            </DialogHeader>
            <div className="flex flex-col gap-3">
              {project.folder && (
                <Button variant="outline" className="justify-start" onClick={() => moveTo("")}>
                  (root — no folder)
                </Button>
              )}
              {existingFolders.map((folder) => (
                <Button key={folder} variant="outline" className="justify-start" onClick={() => moveTo(folder)}>
                  {folder}
                </Button>
              ))}
              <div className="flex gap-2 pt-1 border-t">
                <Input
                  placeholder="New folder name…"
                  value={newFolder}
                  onChange={(e) => setNewFolder(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && newFolder) moveTo(newFolder); }}
                />
                <Button onClick={() => moveTo(newFolder)} disabled={!newFolder}>Move</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

function ImageUploadModal({
  open,
  onOpenChange,
  project,
  user,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: AmcatProject;
  user: AmcatSessionUser;
}) {
  const { mutateAsync, isPending } = useUploadProjectImage(user);
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleUpload() {
    if (!file) return;
    mutateAsync({ projectId: project.id, file }).then(() => {
      setFile(null);
      onOpenChange(false);
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setFile(null); onOpenChange(o); }}>
      <DialogContent className="w-[400px] max-w-[90vw]">
        <DialogHeader>
          <DialogTitle>Project Image</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <Input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/jpg,image/png,image/webp"
            className="w-full font-extralight file:mr-3 file:rounded file:text-foreground"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button onClick={handleUpload} disabled={!file || isPending}>
            {isPending ? "Uploading…" : "Upload image"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Converts bytes to KB, MB, or GB, using 1024 as the base.
 */
function formatSimpleBytes(bytes: number | null): string {
  if (bytes === null) return "Could not determine size";

  const k = 1024;
  const precision = 1;

  if (bytes < k) return bytes + " Bytes";
  if (bytes < k * k) return (bytes / k).toFixed(precision) + " KB";
  if (bytes < k * k * k) return (bytes / (k * k)).toFixed(precision) + " MB";
  return (bytes / (k * k * k)).toFixed(precision) + " GB";
}

function ExportProject({ project }: { project: AmcatProject }) {
  return (
    <Button variant="outline" className="flex gap-2" asChild>
      <a href={`/api/index/${project.id}/download`} download={`${project.id}.ndjson.gz`}>
        <Download className="h-5 w-5" />
        <span className="hidden md:block">Export project</span>
      </a>
    </Button>
  );
}

function ArchiveProject({ project }: { project: AmcatProject }) {
  const { user } = useAmcatSession();
  const { mutate: archive } = useArchiveProject(user);
  const [archiveOpen, setArchiveOpen] = useState(false);

  return (
    <Popover open={archiveOpen} onOpenChange={setArchiveOpen}>
      <PopoverTrigger asChild>
        <Button onClick={() => setArchiveOpen(!archiveOpen)} variant={"outline"} className="flex w-min gap-2">
          <FolderArchive className="h-5 w-5" />
          <span className="hidden md:block">{project.archived ? "Unarchive" : "Archive"}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="flex flex-col gap-3">
        <p>Are you sure you want to {project.archived ? "unarchive" : "archive"} this project?</p>
        <Button
          onClick={() => {
            if (archive) {
              archive({ projectId: project.id, archived: !project.archived });
            }
            setArchiveOpen(false);
          }}
        >
          Yes
        </Button>
      </PopoverContent>
    </Popover>
  );
}

function DeleteProject({ project }: { project: AmcatProject }) {
  const { user } = useAmcatSession();
  const { mutateAsync: deleteAsync, isPending: isDeleting, isError: isDeleteError, error: deleteError, reset: resetDelete } = useDeleteProject(user);
  const navigate = useNavigate();
  const { activate, confirmDialog } = useConfirm();

  async function handleDelete() {
    try {
      await deleteAsync(project.id);
      navigate({ to: "/projects" });
    } catch {
      // error shown in dialog
    }
  }

  return (
    <>
      <Button
        variant="outline"
        className="flex w-min gap-2 border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground"
        onClick={() =>
          activate(handleDelete, {
            description: `You are about to permanently delete project "${project.name}". This cannot be undone!`,
            challenge: project.id,
            confirmText: `Delete project`,
          })
        }
      >
        <Trash2 className="h-5 w-5" />
        <span className="hidden md:block">Delete</span>
      </Button>
      {confirmDialog}
      <Dialog open={isDeleting || isDeleteError} onOpenChange={(open) => !open && resetDelete()}>
        <DialogContent onInteractOutside={(e) => e.preventDefault()} className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{isDeleteError ? "Deletion failed" : "Deleting project..."}</DialogTitle>
            <DialogDescription>
              {isDeleteError
                ? (deleteError as Error)?.message ?? "An unexpected error occurred."
                : `Deleting project "${project.name}". Please wait.`}
            </DialogDescription>
          </DialogHeader>
          {isDeleteError && (
            <div className="flex justify-end">
              <Button variant="outline" onClick={resetDelete}>
                Close
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

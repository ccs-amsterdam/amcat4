import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/projects/$project/settings")({
  component: SettingsPage,
});

import { useArchiveProject, useProject, useMutateProject } from "@/api/project";
import { ContactInfo } from "@/components/Project/ContactInfo";
import { UpdateProject } from "@/components/Project/UpdateProject";
import { Button } from "@/components/ui/button";
import { ErrorMsg } from "@/components/ui/error-message";
import { Loading } from "@/components/ui/loading";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { AmcatProject } from "@/interfaces";
import { Edit, Trash2 } from "lucide-react";
import { AmcatSessionUser, useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useState } from "react";

function SettingsPage() {
  const { project } = Route.useParams();
  const { user } = useAmcatSession();
  const projectId = decodeURI(project);
  const { data: projectData, isLoading: loadingProject } = useProject(user, projectId);

  if (loadingProject) return <Loading />;
  if (!projectData) return <ErrorMsg type="Not Allowed">Need to be logged in</ErrorMsg>;

  return (
    <div className="flex w-full  flex-col gap-10">
      <Settings user={user} project={projectData} />
    </div>
  );
}

function Settings({ user, project }: { user: AmcatSessionUser; project: AmcatProject }) {
  const { mutate } = useMutateProject(user);
  const { mutate: archive } = useArchiveProject(user);
  const [archiveOpen, setArchiveOpen] = useState(false);

  return (
    <div className="grid grid-cols-1 items-start justify-between gap-10 p-3">
      <div>
        <div className="mb-3 flex items-center gap-5 md:justify-between">
          <h2 className="mb-0 mt-0 break-all text-[clamp(1.2rem,5vw,2rem)]">{project.name}</h2>
          <div className="flex items-center gap-2">
            <Popover open={archiveOpen} onOpenChange={setArchiveOpen}>
              <PopoverTrigger asChild>
                <Button
                  onClick={() => setArchiveOpen(!archiveOpen)}
                  variant={!project.archived ? "outline" : "default"}
                  className="flex gap-2"
                >
                  <Trash2 className="h-5 w-5" />
                  {!!project.archived ? "Unarchive" : "Archive"}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="flex flex-col gap-3">
                <p>Are you sure you want to {!!project.archived ? "unarchive" : "archive"} this project?</p>
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
            <UpdateProject project={project}>
              <Button variant="ghost" className="flex gap-3">
                <Edit className="h-7 w-7" />
                <div className="hidden text-xl md:block">Edit</div>
              </Button>
            </UpdateProject>
          </div>
        </div>
        <p className=" mt-0 break-all text-[clamp(0.8rem,3.5vw,1.4rem)]">
          {project.description || <i className="text-sm text-foreground/60">(No description)</i>}
        </p>
      </div>

      <div className="grid grid-cols-[auto,1fr] gap-x-6 text-lg   ">
        <div className="font-bold">Size</div>
        <div className="text-primary">{formatSimpleBytes(project.bytes || null)}</div>
        <div className="font-bold">Guest role</div>
        <div className="text-primary">{project.guest_role}</div>
        <div className="font-bold">Own role</div>
        <div className=" text-primary">{project.user_role}</div>
        <div className="font-bold">Folder</div>
        <div className=" text-primary">{project.folder}</div>
      </div>
      <img
        src={project.image_url || ""}
        alt="No project image set"
        className="max-w-[300px] rounded object-contain text-center"
      />

      <div>
        <div className="prose w-max rounded-md bg-primary/10 px-6 py-2 dark:prose-invert">
          <h4 className="text-foreground/60">Contact information</h4>
          <ContactInfo contact={project.contact} />
        </div>
      </div>
      <div className={`${project.archived ? "" : "hidden"}`}>
        <p className="w-max rounded border border-destructive p-2 text-destructive">
          This project was archived on {project.archived?.split(".")[0]}
        </p>
      </div>
    </div>
  );
}
/**

 * Converts bytes to KB, MB, or GB, using 1024 as the base.
 * @param bytes The size in bytes.
 * @returns A string in the format "X.X UNIT".
 */
function formatSimpleBytes(bytes: number | null): string {
  if (bytes === null) return "Could not determine size";

  const k = 1024;
  const precision = 1;

  if (bytes < k) {
    return bytes + " Bytes";
  }

  if (bytes < k * k) {
    // Less than 1 MB
    return (bytes / k).toFixed(precision) + " KB";
  }

  if (bytes < k * k * k) {
    // Less than 1 GB
    return (bytes / (k * k)).toFixed(precision) + " MB";
  }

  // Default to GB for all larger sizes (>= 1 GB)
  return (bytes / (k * k * k)).toFixed(precision) + " GB";
}

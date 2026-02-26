import { useProject } from "@/api/project";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AmcatProject, AmcatProjectId, RecentProjects } from "@/interfaces";
import { CommandEmpty } from "cmdk";
import { ChevronDown } from "lucide-react";
import { AmcatSessionUser, useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import useLocalStorage from "@/lib/useLocalStorage";

export default function ProjectMenu() {
  const { user } = useAmcatSession();
  const [recentProjectsByUser] = useLocalStorage<RecentProjects>("recentProjects", {});
  const params = useParams({ strict: false }) as any;
  const projectId = decodeURI(params?.project || "");
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const { data: project } = useProject(user, projectId);

  if (!user) return null;

  const key = user?.email || "guest";
  const recentProjects = recentProjectsByUser[key]?.filter((r) => r.id !== projectId) || [];
  const noRecent = recentProjects.length === 0;

  function current() {
    if (projectId)
      return (
        <span className="overflow-hidden text-ellipsis whitespace-nowrap font-semibold">
          {project?.name || project?.id.replace("_", " ")}
        </span>
      );
    return (
      <span className={`overflow-hidden text-ellipsis whitespace-nowrap font-normal text-foreground/80 `}>
        recent project
      </span>
    );
  }

  function onSelectProject(projectId: string) {
    navigate({ to: `/projects/${projectId}/dashboard` });
    setOpen(false);
  }

  return (
    <DropdownMenu open={open && !noRecent} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        disabled={noRecent}
        className={`flex h-full min-w-0  select-none items-center gap-1 px-1 outline-none hover:font-semibold md:px-3 ${open ? "font-semibold" : ""}`}
      >
        {current()}
        {noRecent ? null : <ChevronDown className="h-4 w-4 opacity-50" />}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="ml-2 w-[200px] max-w-[95vw] border-[1px] border-foreground">
        <DropdownMenuLabel>Select project</DropdownMenuLabel>
        {recentProjects.map((project) => {
          return (
            <DropdownMenuItem key={project.id} onClick={() => onSelectProject(project.id)}>
              {project.name}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

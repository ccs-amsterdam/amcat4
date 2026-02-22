import { useIndex } from "@/api/index";
import { useAmcatProjects } from "@/api/projects";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { AmcatIndex, AmcatIndexId, RecentProjects } from "@/interfaces";
import { CommandEmpty } from "cmdk";
import { ChevronDown } from "lucide-react";
import { AmcatSessionUser, useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import useLocalStorage from "@/lib/useLocalStorage";

export default function IndexMenu() {
  const { user } = useAmcatSession();
  const [recentProjectsByUser] = useLocalStorage<RecentProjects>("recentProjects", {});
  const params = useParams({ strict: false }) as any;
  const indexId = decodeURI(params?.project || "");
  const [open, setOpen] = useState(false);

  const { data: index } = useIndex(user, indexId);

  if (!user) return null;

  const key = user?.email || "guest";
  const recentProjects = recentProjectsByUser[key]?.filter((r) => r.id !== indexId) || [];
  const noRecent = recentProjects.length === 0;

  function current() {
    if (indexId)
      return (
        <span className="overflow-hidden text-ellipsis whitespace-nowrap font-semibold">{index?.name || "..."}</span>
      );
    return (
      <span className={`overflow-hidden text-ellipsis whitespace-nowrap font-normal text-foreground/80 `}>
        {noRecent ? "..." : "recent index"}
      </span>
    );
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
        <SelectRecentIndex recentProjects={recentProjects} indexId={indexId} onSelect={() => setOpen(false)} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SelectRecentIndex({
  recentProjects,
  indexId,
  onSelect,
}: {
  recentProjects: AmcatIndex[];
  indexId: AmcatIndexId;
  onSelect: () => void;
}) {
  const navigate = useNavigate();

  function onSelectIndex(index: string) {
    navigate({ to: `/projects/${index}/dashboard` });
    onSelect();
  }

  return (
    <Command>
      <CommandInput placeholder="Recent projects" autoFocus={true} className="h-9" />
      <CommandList>
        <CommandEmpty>No index found</CommandEmpty>
        <CommandGroup>
          {recentProjects.map((index) => {
            if (index.id === indexId) return null;
            if (index.archived) return null;
            return (
              <CommandItem key={index.id} value={index.id} onSelect={(value) => onSelectIndex(value)}>
                <span>{index.name.replaceAll("_", " ")}</span>
              </CommandItem>
            );
          })}
        </CommandGroup>
      </CommandList>
    </Command>
  );
}

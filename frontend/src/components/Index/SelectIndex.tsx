import { useAmcatProjects } from "@/api/projects";
import { useHasGlobalRole } from "@/api/userDetails";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui/loading";
import { AmcatIndex } from "@/interfaces";
import { Folder, FolderOpen, LogInIcon, Search, Settings2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ErrorMsg } from "../ui/error-message";
import { InfoMsg } from "../ui/info-message";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Switch } from "../ui/switch";
import { CreateIndex } from "./CreateIndex";
import { FolderBreadcrumbs } from "./FolderBreadcrumbs";
import { IndexCard } from "./IndexCard";
import { PendingIndexRequests } from "./PendingIndexRequests";
import { useAmcatConfig } from "@/api/config";
import { useQueryState } from "nuqs";

interface Folder {
  folders: Map<string, Folder>;
  projects: AmcatIndex[];
}

export function SelectIndex() {
  const { user } = useAmcatSession();
  const { data: config } = useAmcatConfig();
  const [currentPath, setCurrentPath] = useQueryState("folder");

  const [search, setSearch] = useState("");
  const [indexMap, setIndexMap] = useState<Map<string, AmcatIndex[]> | null>(null);
  const canCreate = useHasGlobalRole(user, "WRITER");
  const isAdmin = useHasGlobalRole(user, "ADMIN");
  const [path, setPath] = useState<string | null>(null);

  const [showArchived, setShowArchived] = useState(false);
  const [showAllProjects, setShowAllProjects] = useState(false);
  const { data: allProjects, isLoading: loadingProjects } = useAmcatProjects(user, {
    showAll: showAllProjects,
    showArchived: showArchived,
  });

  // filter projects based on showAllProjects and showArchived.
  // If no 'own' projects present, show all projects to allow users to request access
  const myProjects = useMemo(() => {
    if (!allProjects) return undefined;

    const hasOwnedProjects = allProjects.some((ix) => ix.user_role !== "NONE" || ix.guest_role !== "NONE");

    return allProjects.filter((ix) => {
      if (!showAllProjects && hasOwnedProjects && ix.user_role === "NONE" && ix.guest_role === "NONE") return false;
      if (!showArchived && ix.archived) return false;
      return true;
    });
  }, [allProjects, showAllProjects, showArchived]);

  // In no_auth mode, set showAllProjects to true by default
  useEffect(() => {
    if (config?.authorization === "no_auth" && !showAllProjects) {
      setShowAllProjects(true);
    }
  }, [allProjects, config]);

  useEffect(() => {
    function setVisible() {
      if (!myProjects) return;

      const filtered = myProjects.filter((index) => {
        if (search) {
          if (index.name.toLowerCase().includes(search.toLowerCase())) return true;
          if (index.id.toLowerCase().includes(search.toLowerCase())) return true;
          return false;
        }
        return true;
      });

      let prefix = currentPath?.replace(/^\/|\/$/, "") ?? "";

      const indexMap = new Map<string, AmcatIndex[]>();
      indexMap.set("", []);

      filtered.forEach((ix) => {
        // remove double slashes and leading/trailing slashes
        const folder = (ix.folder || "").replace(/\/+/g, "/").replace(/^\/|\/$/g, "");

        if (prefix && folder !== prefix && !folder.startsWith(prefix + "/")) return;

        // const head = path.pop() || "";
        const remainingPath = prefix ? folder.slice(prefix.length + 1) : folder;

        const head = remainingPath.split("/")[0] || "";
        if (!indexMap.has(head)) indexMap.set(head, []);
        indexMap.get(head)?.push(ix);
      });

      setPath(prefix);
      setIndexMap(indexMap);
    }

    const timeout = setTimeout(setVisible, 200);
    return () => clearTimeout(timeout);
  }, [myProjects, search, currentPath, showArchived, showAllProjects]);

  function updatePath(path: string | null) {
    // setVisibleFolders([]);
    // setVisibleProjects([]);
    setCurrentPath(path);
  }
  function setFolder(folder: string[]) {
    updatePath(folder.join("/"));
  }
  function appendFolder(add: string) {
    updatePath(currentPath ? currentPath + "/" + add : add);
  }

  if (user && !isAdmin && !user.authenticated && allProjects?.length === 0) return <NoPublicProjectsMessage />;
  if (indexMap === null) return <Loading />;
  const folderList = [...indexMap.keys()].filter((f) => f !== "");

  return (
    <div className="flex flex-col gap-3">
      <div className="mb-8 flex flex-col items-start gap-2 md:flex-row">
        <div className="prose-xl mr-auto   flex items-center justify-between">
          <h3 className="">Projects</h3>
        </div>
        <CreateIndex folder={currentPath ?? undefined} request={!canCreate} />
        <PendingIndexRequests />
      </div>

      <div className="mb-3 flex items-center gap-6">
        <SearchAndFilter
          isAdmin={isAdmin || false}
          search={search}
          setSearch={setSearch}
          showArchived={showArchived}
          setShowArchived={setShowArchived}
          showPublic={showAllProjects}
          setShowPublic={setShowAllProjects}
        />
      </div>

      <div className="grid grid-cols-[min(30vw,250px),1fr] gap-3 rounded bg-gradient-to-tr from-primary/5 to-primary/20">
        <div className="flex h-full min-h-[500px] flex-col rounded-l bg-primary/10 p-3">
          <div className="pb-3">
            <FolderBreadcrumbs currentPath={path} toFolder={updatePath} />
          </div>
          {/*<div className="px-1 pb-3 font-semibold text-foreground/60">Folders</div>*/}
          {/*<Button
            size="sm"
            variant="ghost"
            className={`${path ? "flex" : "hidden"}  h-8 items-center justify-start gap-3 px-1 text-foreground/50 `}
            onClick={() => setFolder((path?.split("/") ?? []).slice(0, -1))}
          >
            <Undo className="h-4 w-4" />
            back
          </Button>*/}

          {folderList.map((folder) => (
            <ProjectFolder key={folder} folder={folder} onClick={() => appendFolder(folder)} />
          ))}
          {folderList?.length || path ? null : (
            <div className="px-1 py-1 text-sm text-foreground/60">No folders found</div>
          )}
        </div>
        {indexMap.size === 0 ? (
          <NoResultsMessage cancreate={!!canCreate} issearching={search !== ""} />
        ) : (
          <div className="flex flex-col ">
            <div className="mb-6 mt-3 min-h-[50rem] rounded p-3">
              {loadingProjects ? <Loading /> : null}
              {[...indexMap].map(([folder, projects], i) => {
                // if (search === "" && folder !== "") return null;
                if (projects.length === 0) {
                  return null;
                }
                if (loadingProjects) return null;

                return (
                  <div key={folder} className="mb-12">
                    <div
                      className={`${folder === "" ? "hidden" : ""} mb-1 flex items-center gap-1 text-sm text-foreground/60`}
                    >
                      {/*Projects in folder*/}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="my-1 flex h-6 w-full items-center gap-2 px-1 py-4 hover:bg-background/20"
                        onClick={() => appendFolder(folder)}
                      >
                        <Folder className="h-5 w-5" />
                        {folder}
                        <div className={"flex-auto  border-b border-foreground/20 "} />
                      </Button>
                    </div>
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-[repeat(auto-fill,minmax(280px,1fr))]">
                      {projects.map((index) => (
                        <IndexCard key={index.id} index={index} folders={folderList} toFolder={setCurrentPath} />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SearchAndFilter({
  isAdmin,
  search,
  setSearch,
  showArchived,
  setShowArchived,
  showPublic,
  setShowPublic,
}: {
  isAdmin: boolean;
  search: string;
  setSearch: (s: string) => void;
  showArchived: boolean;
  setShowArchived: (b: boolean) => void;
  showPublic: boolean;
  setShowPublic: (b: boolean) => void;
}) {
  return (
    <div className={`Pagination ml-auto flex select-none items-center gap-3  `}>
      <div className="relative flex items-center gap-2">
        <Search className="absolute left-1 h-5 w-5 text-foreground/20" />
        <Input
          className="w-44 rounded-none border-0  border-b pl-9 focus-visible:ring-0"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search"
        />
      </div>
      <Popover>
        <PopoverTrigger>
          <Settings2 />
        </PopoverTrigger>
        <PopoverContent className="flex flex-col gap-2">
          <div className={`${isAdmin ? "" : "hidden"} flex  items-center gap-3`}>
            <Switch className="size-3" id="seeAll" checked={showPublic} onCheckedChange={setShowPublic} />
            <Label htmlFor="seeAll">show all projects</Label>
          </div>
          <div className={`flex  items-center gap-3`}>
            <Switch className="size-3" id="seeArchived" checked={showArchived} onCheckedChange={setShowArchived} />
            <Label htmlFor="seeArchived">show archived</Label>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

const ProjectFolder = ({ folder, onClick }: { folder: string; onClick: () => void }) => (
  <Button
    variant="ghost"
    size="sm"
    className="group flex h-8 min-h-0 items-center justify-start gap-3 px-1 py-1"
    onClick={onClick}
  >
    <Folder className={`h-4 w-4 group-hover:hidden`} />
    <FolderOpen className={`hidden h-4 w-4 group-hover:block`} />
    <span
      className="max-w-16 overflow-hidden text-ellipsis text-nowrap text-sm md:max-w-32 md:text-base"
      title={folder}
    >
      {folder}
    </span>
  </Button>
);

function NoPublicProjectsMessage({}: {}) {
  const { signIn } = useAmcatSession();

  return (
    <ErrorMsg type="No public projects">
      <p className="w-[500px] max-w-[95vw] text-center">
        There are no public projects on this server. Please sign-in to see if you have access to any projects. Signed in
        users can also request the creation of new projects.
      </p>
      <Button className="mx-auto mt-6 flex items-center gap-2 pr-6" onClick={() => signIn()}>
        <LogInIcon className="mr-2 h-4 w-4" />
        Sign-in
      </Button>
    </ErrorMsg>
  );
}
function NoResultsMessage({ cancreate, issearching }: { cancreate: boolean; issearching: boolean }) {
  return (
    <InfoMsg type="No projects">
      <p className="w-[500px] max-w-[95vw] text-center">
        {issearching
          ? "No projects match your search pattern. Try changing your search terms or filter options. "
          : "There are currently no projects that you have access to. "}
        {cancreate
          ? "To get started, create a new index using the 'create new (index)' button above"
          : "To get started, you can ask a server administrator to create a project for you using the 'Request new (index)' button above "}
      </p>
    </InfoMsg>
  );
}

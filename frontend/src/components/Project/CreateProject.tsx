import { useCreateProject, useRegisterProject, useUnregisteredIndices } from "@/api/project";
import { useSubmitRequest } from "@/api/requests";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { amcatProjectSchema } from "@/schemas";
import { useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { useHasGlobalRole } from "@/api/userDetails";
import { AmcatRequestProject } from "@/interfaces";
import { Check, ChevronsUpDown, Loader } from "lucide-react";
import { useQueryState } from "nuqs";

export function CreateProject({ folder, request }: { folder?: string; request?: boolean }) {
  const navigate = useNavigate();
  const [open, setOpen] = useQueryState("create_project");

  const [loading, setLoading] = useState(false);
  const { user } = useAmcatSession();
  const isAdmin = useHasGlobalRole(user, "ADMIN");

  const { mutateAsync: createProjectAsync } = useCreateProject(user);
  const { mutateAsync: registerProjectAsync } = useRegisterProject(user);
  const { mutateAsync: requestProjectAsync } = useSubmitRequest(user);
  const { data: unregisteredIndices } = useUnregisteredIndices(isAdmin ? user : undefined);
  const [name, setName] = useState("");
  const [folderValue, setFolderValue] = useState(folder);
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState("");
  const [id, setId] = useState("");
  const [registerId, setRegisterId] = useState("");
  const [indexSearch, setIndexSearch] = useState("");
  const [comboOpen, setComboOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setFolderValue(folder);
  }, [folder]);

  if (!isAdmin && !user?.authenticated) return null;

  function idFromName(name: string) {
    return name
      .replaceAll(" ", "-")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replaceAll(/[^a-z0-9_-]/g, "")
      .replace(/^[_-]+/, "");
  }

  function onCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    createProjectAsync(amcatProjectSchema.parse({ id, name, description, folder: folderValue }))
      .then(() => navigate({ to: `/projects/${id}/data`, search: { tab: "upload" } as any }))
      .catch((e) => {
        setError(e?.response?.data?.message || "An error occurred");
      })
      .finally(() => setTimeout(() => setLoading(false), 500));
  }

  function onRegister(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    registerProjectAsync(amcatProjectSchema.parse({ id: registerId, name, description, folder: folderValue }))
      .then(() => navigate({ to: `/projects/${registerId}/dashboard` }))
      .catch((e) => {
        setError(e?.response?.data?.detail || e?.response?.data?.message || "An error occurred");
      })
      .finally(() => setTimeout(() => setLoading(false), 500));
  }

  function onRequest(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!user) return;
    const request: AmcatRequestProject = {
      type: "create_project",
      project_id: id,
      name: name,
      description: description,
      message: message,
    };

    setLoading(true);
    requestProjectAsync(request)
      .then(() => {
        setOpen(null);
      })
      .finally(() => setTimeout(() => setLoading(false), 500));
  }

  function requestInfo() {
    if (!request) return null;
    return (
      <div className="prose dark:prose-invert">
        You do not have permission to create a new project, but you can submit a request. If approved, the project will
        be created for you and you will be granted admin access to it.
      </div>
    );
  }

  function sharedFields() {
    return (
      <>
        <div className="flex items-center justify-between gap-6">
          <div>
            <label htmlFor="name">Name</label>
            <Input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setId(idFromName(e.target.value));
              }}
              id="name"
              name="name"
              autoComplete="off"
              placeholder="My new project"
            />
          </div>

          <div>
            <label htmlFor="ID">Project ID</label>
            <Input id="ID" name="ID" value={id} onChange={(e) => setId(idFromName(e.target.value))} />
          </div>
        </div>
        <div>
          <label htmlFor="description">Description</label>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            id="description"
            name="description"
            placeholder="Optionally, A brief description of the project"
          />
        </div>
        <div>
          <label htmlFor="folder">Folder</label>
          <Input
            value={folderValue}
            onChange={(e) => {
              setFolderValue(e.target.value);
            }}
            id="folder"
            name="folder"
            placeholder="newspapers/national"
            autoComplete="off"
          />
        </div>
      </>
    );
  }

  if (request) {
    return (
      <Dialog open={!!open} onOpenChange={(open) => setOpen(open ? "open" : null)}>
        <DialogTrigger asChild>
          <Button className="">Request new project</Button>
        </DialogTrigger>
        <DialogContent aria-describedby={undefined} className="w-[600px] max-w-[95vw]">
          <DialogHeader>
            <DialogTitle>Request Project</DialogTitle>
          </DialogHeader>
          <form className="flex flex-col gap-3" onSubmit={onRequest}>
            {requestInfo()}
            {sharedFields()}
            <div>
              <label htmlFor="message">Project request Message</label>
              <Textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                id="message"
                name="message"
                placeholder="You can add a message here to justify your request."
              />
            </div>
            <div className={`${error ? "" : "hidden"} text-center text-destructive`}>{error}</div>
            <Button className="mt-2 w-full">
              {loading ? <Loader className="mr-2 h-4 w-4 animate-spin" /> : "Submit request"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog
      open={!!open}
      onOpenChange={(open) => {
        setOpen(open ? "open" : null);
        setError(null);
      }}
    >
      <DialogTrigger asChild>
        <Button className="">Create new project</Button>
      </DialogTrigger>
      <DialogContent aria-describedby={undefined} className="w-[600px] max-w-[95vw]">
        <DialogHeader>
          <DialogTitle>Create Project</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="create" onValueChange={() => setError(null)}>
          <TabsList>
            <TabsTrigger value="create">Create new</TabsTrigger>
            <TabsTrigger value="register">Register existing</TabsTrigger>
          </TabsList>
          <TabsContent value="create">
            <form className="flex flex-col gap-3 pt-2" onSubmit={onCreate}>
              {sharedFields()}
              <div className={`${error ? "" : "hidden"} text-center text-destructive`}>{error}</div>
              <Button className="mt-2 w-full">
                {loading ? <Loader className="mr-2 h-4 w-4 animate-spin" /> : "Create project"}
              </Button>
            </form>
          </TabsContent>
          <TabsContent value="register">
            <form className="flex flex-col gap-3 pt-2" onSubmit={onRegister}>
              <div className="prose dark:prose-invert text-sm">
                Register an existing Elasticsearch index as an amcat project. The index must already exist.
              </div>
              <div className="flex flex-col gap-1">
                <label>Elasticsearch Index</label>
                <Popover open={comboOpen} onOpenChange={setComboOpen}>
                  <PopoverTrigger asChild>
                    <Button variant="outline" role="combobox" aria-expanded={comboOpen} className="justify-between font-normal">
                      {registerId || "Select an index…"}
                      <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[--radix-popover-trigger-width] p-0">
                    <div className="flex flex-col">
                      <Input
                        placeholder="Search indices…"
                        value={indexSearch}
                        onChange={(e) => setIndexSearch(e.target.value)}
                        className="rounded-none border-0 border-b focus-visible:ring-0"
                        autoFocus
                      />
                      <div className="max-h-60 overflow-y-auto">
                        {(unregisteredIndices ?? []).filter((ix) => ix.includes(indexSearch)).length === 0 ? (
                          <p className="p-2 text-sm text-foreground/60">No unregistered indices found.</p>
                        ) : (
                          (unregisteredIndices ?? [])
                            .filter((ix) => ix.includes(indexSearch))
                            .map((ix) => (
                              <button
                                key={ix}
                                type="button"
                                className={`flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-accent ${registerId === ix ? "bg-accent" : ""}`}
                                onClick={() => {
                                  setRegisterId(ix);
                                  setName(ix);
                                  setComboOpen(false);
                                }}
                              >
                                <Check className={`h-4 w-4 shrink-0 ${registerId === ix ? "opacity-100" : "opacity-0"}`} />
                                {ix}
                              </button>
                            ))
                        )}
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
              <div>
                <label htmlFor="reg-name">Name</label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  id="reg-name"
                  name="name"
                  autoComplete="off"
                  placeholder="My project name"
                />
              </div>
              <div>
                <label htmlFor="reg-description">Description</label>
                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  id="reg-description"
                  name="description"
                  placeholder="Optionally, a brief description of the project"
                />
              </div>
              <div>
                <label htmlFor="reg-folder">Folder</label>
                <Input
                  value={folderValue}
                  onChange={(e) => setFolderValue(e.target.value)}
                  id="reg-folder"
                  name="folder"
                  placeholder="newspapers/national"
                  autoComplete="off"
                />
              </div>
              <div className={`${error ? "" : "hidden"} text-center text-destructive`}>{error}</div>
              <Button className="mt-2 w-full" disabled={!registerId}>
                {loading ? <Loader className="mr-2 h-4 w-4 animate-spin" /> : "Register project"}
              </Button>
            </form>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

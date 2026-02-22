import { useRequests, useResolveRequests } from "@/api/requests";
import { AmcatRequest, AmcatRequestProject, AmcatRequestProjectRole, AmcatRequestServerRole } from "@/interfaces";
import { Bell, Check, CheckIcon, Loader, X } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useEffect, useMemo, useState } from "react";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";

type Tab = "Server role" | "Index role" | "Project";

interface Action {
  tab: Tab;
  decision: "approved" | "rejected";
  request: AmcatRequest;
}

export function Notifications() {
  const { user } = useAmcatSession();
  const { data: requests } = useRequests(user);
  const [actions, setActions] = useState<Record<string, Action>>({});

  return <NotificationModal requests={requests || []} actions={actions} setActions={setActions} />;
}

interface NotificationProps {
  requests: AmcatRequest[];
  actions: Record<string, Action>;
  setActions: React.Dispatch<React.SetStateAction<Record<string, Action>>>;
}

function NotificationModal({ requests, actions, setActions }: NotificationProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const { user } = useAmcatSession();
  const { mutateAsync: resolveRequests } = useResolveRequests(user);

  const done = Object.keys(actions).length;
  const n = requests.length;
  if (n === 0) return null;

  function onResolve() {
    const resolvedRequests: AmcatRequest[] = Object.values(actions).map((a) => ({
      ...a.request,
      status: a.decision,
    }));

    setLoading(true);
    resolveRequests(resolvedRequests)
      .then(() => {
        setActions({});
        setOpen(false);
      })
      .finally(() => setLoading(false));
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger className="relative flex h-full select-none items-center gap-3 border-primary px-2 outline-none hover:bg-primary/10 lg:px-4">
        <Bell />
        <div className="absolute left-6 top-1 text-xs lg:left-9">{n > 99 ? "99+" : n}</div>
      </DialogTrigger>
      <DialogContent
        onPointerDownOutside={(e) => (done ? e.preventDefault() : null)}
        className="prose flex h-[500px] max-h-[90vh] w-[700px] max-w-[95vw] flex-col  items-stretch  py-6 dark:prose-invert"
      >
        <DialogHeader>
          <DialogTitle className="mt-0">Notifications</DialogTitle>
          <DialogDescription className="h-0 opacity-0">Your have {n} notifications</DialogDescription>
        </DialogHeader>

        <NotificationTabs requests={requests} actions={actions} setActions={setActions} />
        <div className="mt-auto flex items-center justify-end gap-3">
          <div>
            {done} / {n} requests evaluated
          </div>
          <Button onClick={onResolve} disabled={Object.keys(actions).length === 0} className="w-40">
            {loading ? <Loader className="mr-2 h-4 w-4 animate-spin" /> : "Submit decisions"}
          </Button>
          <Button
            variant="outline"
            className="bg-foreground/10"
            onClick={() => {
              setActions({});
              setOpen(false);
            }}
          >
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function NotificationTabs({ requests, actions: actions, setActions }: NotificationProps) {
  const [tab, setTab] = useState<Tab>("Server role");

  const requestsPerTab = useMemo(() => {
    const requestsPerTab: Record<Tab, AmcatRequest[]> = { "Server role": [], "Index role": [], Project: [] };
    requestsPerTab["Server role"] = requests.filter((r) => r.request.type === "server_role");
    requestsPerTab["Index role"] = requests.filter((r) => r.request.type === "project_role");
    requestsPerTab["Project"] = requests.filter((r) => r.request.type === "create_project");
    return requestsPerTab;
  }, [requests]);

  useEffect(() => {
    setTab((tab) => {
      const currentTabTodo = requestsPerTab[tab].length - Object.values(actions).filter((a) => a.tab === tab).length;
      if (currentTabTodo === 0) {
        for (const t of Object.keys(requestsPerTab) as Tab[]) {
          const otherTabTodo = requestsPerTab[t].length - Object.values(actions).filter((a) => a.tab === t).length;
          if (otherTabTodo > 0) return t;
        }
      }
      return tab;
    });
  }, [actions, requestsPerTab]);

  function setApproveHandler(tab: Tab, key: string, request: AmcatRequest, decision: Action["decision"]) {
    setActions((actions) => {
      const key = JSON.stringify(request);
      actions[key] = { tab, request, decision };
      return { ...actions };
    });
  }

  function renderRoleRequests(tab: Tab) {
    return requestsPerTab[tab].map((roleRequest) => {
      const key = JSON.stringify(roleRequest);
      return (
        <RoleRequest
          key={key}
          roleRequest={roleRequest}
          decision={actions[key]?.decision}
          setApprove={(action) => setApproveHandler(tab, key, roleRequest, action)}
        />
      );
    });
  }
  function renderProjectRequests() {
    return requestsPerTab["Project"].map((projectRequest) => {
      const key = JSON.stringify(projectRequest);
      return (
        <ProjectRequest
          key={key}
          projectRequest={projectRequest}
          decision={actions[key]?.decision}
          setApprove={(action) => setApproveHandler(tab, key, projectRequest, action)}
        />
      );
    });
  }

  function renderTrigger(tab: Tab, requests: AmcatRequest[]) {
    const n = requests.length;
    const done = Object.values(actions).filter((a) => a.tab === tab).length;
    return (
      <TabsTrigger value={tab} className="text-sm data-[state=active]:text-sm">
        <NumberBadge text={tab} n={n} done={done} />
      </TabsTrigger>
    );
  }

  return (
    <Tabs className="m-0 " value={tab} onValueChange={(v) => setTab(v as Tab)}>
      <TabsList className="ml-auto flex-col md:flex-row">
        {renderTrigger("Server role", requestsPerTab["Server role"])}
        {renderTrigger("Index role", requestsPerTab["Index role"])}
        {renderTrigger("Project", requestsPerTab["Project"])}
      </TabsList>
      <div className="max-h-[500px] overflow-auto pt-3">
        <TabsContent value="Server role" className="">
          <div className="mt-0 flex flex-col gap-3">{renderRoleRequests("Server role")}</div>
        </TabsContent>
        <TabsContent value="Index role" className="">
          <div className="mt-0 flex flex-col gap-3">
            <div className="mt-0 flex flex-col gap-3">{renderRoleRequests("Index role")}</div>
          </div>
        </TabsContent>
        <TabsContent value="Project" className="">
          <div className="mt-0 flex flex-col gap-3">
            <div className="mt-0 flex flex-col gap-3">{renderProjectRequests()}</div>
          </div>
        </TabsContent>
      </div>
    </Tabs>
  );
}

function NumberBadge({ text, n, done }: { text: string; n: number; done: number }) {
  if (n === 0) return text;
  return (
    <div className="flex items-center gap-3">
      {text}
      <div className=" flex h-5 w-5  items-center justify-center rounded-full  border border-primary bg-background/40 text-xs text-foreground">
        {done === n ? <CheckIcon className="h-3 w-3" /> : n - done}
      </div>
    </div>
  );
}

function RoleRequest({
  roleRequest,
  decision,
  setApprove: setDecision,
}: {
  roleRequest: AmcatRequest;
  decision: Action["decision"] | undefined;
  setApprove: (action: Action["decision"]) => void;
}) {
  const { email, request } = roleRequest;

  if (request.type !== "server_role" && request.type !== "project_role") return null;
  const projectId = request.type === "project_role" ? request.project_id : null;

  const bg =
    decision === "approved" ? "bg-check/30" : decision === "rejected" ? "bg-destructive/30" : "bg-foreground/10";

  return (
    <div className={`${bg} flex flex-col items-end  gap-3 rounded-sm p-3 md:flex-row`}>
      <div className="w-full">
        <div className="text grid grid-cols-[5rem,auto] leading-5">
          <div className="text-foreground/70">user</div>
          <div className="w-full break-words font-bold">{email}</div>
          <div className="text-foreground/70">requests</div>
          <div>{request.role} role</div>
          {projectId == null ? null : (
            <>
              <div className="text-foreground/70">for index</div>
              <b>{projectId}</b>
            </>
          )}
        </div>
        <div className="mt-3 italic">{request.message}</div>
      </div>
      <div className="mb-auto ml-auto flex flex-auto items-center gap-2">
        <Button
          size="sm"
          variant={decision === "approved" ? "positive" : "outline"}
          className={decision === "approved" ? "" : "opacity-50"}
          onClick={() => setDecision("approved")}
        >
          <Check />
        </Button>
        <Button
          size="sm"
          variant={decision === "rejected" ? "destructive" : "outline"}
          className={decision === "rejected" ? "" : "opacity-50"}
          onClick={() => setDecision("rejected")}
        >
          <X />
        </Button>
      </div>
    </div>
  );
}

function ProjectRequest({
  projectRequest,
  decision,
  setApprove: setDecision,
}: {
  projectRequest: AmcatRequest;
  decision: Action["decision"] | undefined;
  setApprove: (action: Action["decision"]) => void;
}) {
  if (projectRequest.request.type !== "create_project") return null;
  const {
    email,
    request: { folder, project_id, message, name, description },
  } = projectRequest;

  const bg =
    decision === "approved" ? "bg-check/30" : decision === "rejected" ? "bg-destructive/30" : "bg-foreground/10";

  return (
    <div className={`${bg} flex flex-col items-end  gap-3 rounded-sm p-3 md:flex-row`}>
      <div className="w-full">
        <div>
          <b>{email}</b> requests project
        </div>
        <div className="text mt-2 grid grid-cols-[7rem,auto] leading-5">
          <div className="text-foreground/70">id</div>
          <div className="w-full break-words font-bold">{project_id}</div>
          <div className="text-foreground/70">name</div>
          <div className="w-full break-words font-bold">{name}</div>
          {!!description && (
            <>
              <div className="text-foreground/70">description</div>
              <div className="w-full break-words font-bold">{description}</div>
            </>
          )}
          {!!folder && (
            <>
              <div className="text-foreground/70">folder</div>
              <div className="w-full break-words font-bold">{folder}</div>
            </>
          )}
        </div>
        <div className="mt-3 italic">{message}</div>
      </div>
      <div className="mb-auto ml-auto flex flex-auto items-center gap-2">
        <Button
          size="sm"
          variant={decision === "approved" ? "positive" : "outline"}
          className={decision === "approved" ? "" : "opacity-50"}
          onClick={() => setDecision("approved")}
        >
          <Check />
        </Button>
        <Button
          size="sm"
          variant={decision === "rejected" ? "destructive" : "outline"}
          className={decision === "rejected" ? "" : "opacity-50"}
          onClick={() => setDecision("rejected")}
        >
          <X />
        </Button>
      </div>
    </div>
  );
}

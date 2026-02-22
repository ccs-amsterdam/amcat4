import { useDeleteMyRequest, useMyRequests, useSubmitRequest } from "@/api/requests";
import { AmcatRequest, AmcatRequestProject } from "@/interfaces";
import { Loader } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useMemo, useState } from "react";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog";

export function PendingIndexRequests() {
  const { user } = useAmcatSession();
  const { data: myRequests, isLoading } = useMyRequests(user);
  const { mutateAsync: deleteRequest } = useDeleteMyRequest(user);

  const pending = useMemo(() => {
    if (!myRequests) return null;
    return myRequests.filter((r) => r.request.type === "create_project").map((r) => r.request as AmcatRequestProject);
  }, [myRequests]);

  async function cancelRequest(request: AmcatRequestProject) {
    deleteRequest(request);
  }

  if (!pending || pending.length === 0) return null;

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline">{pending.length} Pending requests</Button>
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] w-[90vw] max-w-2xl overflow-auto">
        <DialogHeader>
          <DialogTitle>Pending project requests</DialogTitle>
          <DialogDescription>You submitted the following index requests</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1">
          {pending.map((request) => (
            <PendingRequest key={request.project_id} request={request} submitRequest={cancelRequest} />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PendingRequest({
  request,
  submitRequest,
}: {
  request: AmcatRequestProject;
  submitRequest: (request: AmcatRequestProject) => Promise<void>;
}) {
  const [loading, setLoading] = useState(false);

  function onCancel() {
    setLoading(true);
    submitRequest(request).finally(() => setLoading(false));
  }

  return (
    <div className="relative grid grid-cols-[1fr,8rem] rounded bg-foreground/10 p-3 ">
      <div
        className={`${loading ? "" : "hidden"} absolute flex h-full w-full items-center justify-center rounded bg-foreground/30 backdrop-blur-[2px]`}
      >
        <Loader className="h-7 w-7 animate-spin text-primary" />
      </div>
      <div className="text mt-2 grid grid-cols-[7rem,auto] leading-5">
        <div className="text-foreground/70">id</div>
        <div className="w-full break-words font-bold">{request.project_id}</div>
        <div className="text-foreground/70">name</div>
        <div className="w-full break-words font-bold">{request.name}</div>
        {!!request.description && (
          <>
            <div className="text-foreground/70">description</div>
            <div className="w-full break-words font-bold">{request.description}</div>
          </>
        )}
        {!!request.folder && (
          <>
            <div className="text-foreground/70">folder</div>
            <div className="w-full break-words font-bold">{request.folder}</div>
          </>
        )}
      </div>
      <Button className="self-center" variant="destructive" onClick={onCancel} disabled={loading}>
        cancel
      </Button>
    </div>
  );
}

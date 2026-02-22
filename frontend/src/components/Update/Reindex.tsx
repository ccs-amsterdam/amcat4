import { useCount } from "@/api/aggregate";
import { useAmcatProjects } from "@/api/projects";
import { postReindex } from "@/api/query";
import { AmcatIndex, AmcatIndexId, AmcatQuery } from "@/interfaces";
import { DialogDescription, DialogTitle } from "@radix-ui/react-dialog";
import { DropdownMenuContent } from "@radix-ui/react-dropdown-menu";
import { ArrowRight, BarChart, CheckCircle, ChevronDown } from "lucide-react";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "../ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "../ui/dialog";
import { DropdownMenu, DropdownMenuTrigger } from "../ui/dropdown-menu";

interface Props {
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  query: AmcatQuery;
}

export default function Reindex({ user, indexId, query }: Props) {
  const { count } = useCount(user, indexId, query);
  const { data: projects } = useAmcatProjects(user);
  const [newIndexOpen, setNewIndexOpen] = useState(false);
  const [taskResult, setTaskResult] = useState<string | null>(null);
  const [newIndex, setNewIndex] = useState<AmcatIndex | undefined>(undefined);
  //TODO: Add option to create a new index?

  function onSubmitNewIndex(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (newIndex) {
      postReindex(user, indexId, newIndex.id, query)
        .catch((error) => console.error(error))
        .then((res) => {
          setTaskResult(res?.data.task);
        });
    }
  }
  const indexlabel = (ix: AmcatIndex) => `${ix.folder || ""}/${ix.name}`;
  const onSelectNewIndex = (ix: AmcatIndex) => {
    setNewIndex(ix);
    setNewIndexOpen(false); // Close the dropdown
  };
  if (count == null) return null;
  return (
    <div className="flex flex-col gap-6">
      <CopyOperationDialog
        open={taskResult != null}
        onOpenChange={() => setTaskResult(null)}
        newIndexId={newIndex?.id}
        taskResultId={taskResult ?? undefined}
      />
      <h4>
        Copy <b className="text-primary">{count}</b> documents to an existing index
      </h4>

      <form onSubmit={onSubmitNewIndex} className="flex items-center justify-stretch gap-3">
        <DropdownMenu open={newIndexOpen} onOpenChange={setNewIndexOpen}>
          <DropdownMenuTrigger asChild>
            <Button className="min-w-64 justify-between gap-3" variant="outline">
              {newIndex?.name ?? "Select destination index"}

              <ChevronDown className="h-5 w-5" />
            </Button>
          </DropdownMenuTrigger>

          <DropdownMenuContent
            align="start"
            className="ml-2 min-w-[200px] border-[1px] border-foreground bg-background"
          >
            <Command>
              <CommandInput placeholder="Filter projects" autoFocus={true} className="h-9" />
              <CommandList>
                <CommandEmpty>No index found</CommandEmpty>
                <CommandGroup>
                  {projects
                    ?.sort((a, b) => indexlabel(a).localeCompare(indexlabel(b)))
                    .filter((ix) => !user.authenticated || ix.user_role === "WRITER" || ix.user_role === "ADMIN")
                    .filter((ix) => !ix.archived)
                    .map((ix) => (
                      <CommandItem key={ix.id} value={ix.id} onSelect={() => onSelectNewIndex(ix)}>
                        {" "}
                        <span>{indexlabel(ix).replace(/^\//, "")}</span>
                      </CommandItem>
                    ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button type="submit" disabled={newIndex == null}>
          Copy
        </Button>
      </form>

      <div className="border-primary-100 mt-3 border bg-primary/10 p-1">
        <em>Note:</em> This will copy all currently selected articles to a new or existing index. This also allows you
        to change field settings by first creating the target index and defining any fields as needed. Fields in the
        source index that don't occur in the target index will be copied.
      </div>
    </div>
  );
}
interface CopyOperationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  newIndexId?: string;
  taskResultId?: string;
}
function CopyOperationDialog({ open, onOpenChange, newIndexId, taskResultId }: CopyOperationDialogProps) {
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
            <Link href={`/projects/${newIndexId}/dashboard`}>
              View Destination Index
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" className="justify-between">
            <Link href={`/task/${taskResultId}`}>
              View Copy Progress
              <BarChart className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Close and Return to Source Index</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

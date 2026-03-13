import { AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useCount } from "@/api/aggregate";
import { useDeleteByQuery } from "@/api/updateByQuery";
import { useConfirm } from "../ui/confirm";
import { Button } from "../ui/button";
import { Trash2 } from "lucide-react";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  onSuccess?: () => void;
}

export default function DeleteDocuments({ user, projectId, query, onSuccess }: Props) {
  const { count } = useCount(user, projectId, query);
  const { mutateAsync, isPending } = useDeleteByQuery(user, projectId);
  const { activate, confirmDialog } = useConfirm();

  const handleDelete = () => {
    activate(() => mutateAsync({ query }).then(() => onSuccess?.()), {
      title: "Delete documents",
      description: `This will permanently delete ${count} document${count === 1 ? "" : "s"}. This cannot be undone.`,
      danger: true,
      confirmText: "Delete",
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <Button variant="destructive" disabled={!count || isPending} onClick={handleDelete} className="flex w-max gap-2">
        <Trash2 className="h-4 w-4" />
        Delete {count ?? "..."} documents
      </Button>
      <p className="text-sm text-muted-foreground">
        Permanently delete all {count ?? "..."} document{count === 1 ? "" : "s"} matching the current query. This
        action cannot be undone.
      </p>
      {confirmDialog}
    </div>
  );
}

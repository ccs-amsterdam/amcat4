import { AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useFieldValues } from "@/api/fieldValues";
import { Tag } from "lucide-react";
import { Loading } from "../ui/loading";
import { useMutateTags } from "@/api/tags";
import { useState } from "react";
import { Button } from "../ui/button";
import { ValueSelector } from "../ui/value-selector";
import CodeExample from "@/components/CodeExample/CodeExample";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  field: string;
}

export default function AddOrRemoveTag({ user, projectId, query, field }: Props) {
  const { data: fieldValues, isLoading } = useFieldValues(user, projectId, field);
  const [tag, setTag] = useState("");
  const [action, setAction] = useState<"add" | "remove">("add");
  const tagExists = !!tag && fieldValues?.includes(tag);
  const { mutateAsync } = useMutateTags(user, projectId);

  if (isLoading) return <Loading />;

  const onSubmit = () => {
    if (!tag) return;
    mutateAsync({ tag, action, field, query }).then(() => setTag(""));
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Select value={action} onValueChange={(v) => setAction(v as "add" | "remove")}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="add">Add tag</SelectItem>
            <SelectItem value="remove">Remove tag</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex-1">
          <ValueSelector
            values={fieldValues ?? []}
            value={tag}
            onChange={setTag}
            placeholder="Select or create tag"
            valuesLabel="Existing tags"
            icon={<Tag className="h-4 w-4" />}
            inputPlaceholder="Enter new tag…"
          />
        </div>
      </div>
      <div className={tag ? "" : "hidden"}>
        <div className="flex items-center gap-2">
          <Button
            variant={action === "remove" ? "destructive" : "default"}
            disabled={action === "remove" && !tagExists}
            onClick={onSubmit}
            className="flex-1"
          >
            {action === "add" ? "Add" : "Remove"} tag {action === "add" ? "to" : "from"} documents
          </Button>
          <CodeExample action="update_tags" projectId={projectId} query={query} field={field} tag={tag} tagAction={action} />
        </div>
      </div>
    </div>
  );
}

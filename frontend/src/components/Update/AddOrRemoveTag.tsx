import { AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useFieldValues } from "@/api/fieldValues";
import { MessageCircle, Tag, Trash2 } from "lucide-react";
import { Loading } from "../ui/loading";
import { useMutateTags } from "@/api/tags";
import { useState } from "react";
import { Button } from "../ui/button";
import { ValueSelector } from "../ui/value-selector";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  field: string;
}

export default function AddOrRemoveTag({ user, projectId, query, field }: Props) {
  const { data: fieldValues, isLoading } = useFieldValues(user, projectId, field);
  const [tag, setTag] = useState("");
  const tagExists = !!tag && fieldValues?.includes(tag);
  const { mutateAsync } = useMutateTags(user, projectId);

  if (isLoading) return <Loading />;

  const onSubmit = (action: "add" | "remove") => {
    if (!tag) return;
    mutateAsync({ tag, action, field, query }).then(() => setTag(""));
  };

  return (
    <div className="flex flex-col gap-3">
      <ValueSelector
        values={fieldValues ?? []}
        value={tag}
        onChange={setTag}
        placeholder="Select or create tag"
        valuesLabel="Existing tags"
        icon={<Tag className="h-4 w-4" />}
        inputPlaceholder="Enter new tag…"
      />
      <div className={tag ? "" : "hidden"}>
        <div className="flex gap-3">
          <Button className="flex items-center gap-3" onClick={() => onSubmit("add")}>
            <MessageCircle />
            Add tag to documents
          </Button>
          <Button
            className="flex items-center gap-3"
            variant="destructive"
            disabled={!tagExists}
            onClick={() => onSubmit("remove")}
          >
            <Trash2 />
            Remove tag from documents
          </Button>
        </div>
      </div>
    </div>
  );
}

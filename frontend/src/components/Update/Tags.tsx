import { AggregationOptions, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import AggregateResult from "../Aggregate/AggregateResult";
import { useFields } from "@/api/fields";
import { useFieldValues } from "@/api/fieldValues";
import { ChevronDown, MessageCircle, Plus, Tag, Trash2 } from "lucide-react";
import { Loading } from "../ui/loading";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Input } from "../ui/input";
import { useMutateTags } from "@/api/tags";
import { useState } from "react";
import { DynamicIcon } from "../ui/dynamic-icon";
import { Button } from "../ui/button";
import { useCount } from "@/api/aggregate";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
}

export default function Tags({ user, projectId, query }: Props) {
  const { data: fields, isLoading: fieldsLoading } = useFields(user, projectId);
  const [field, setField] = useState("");
  const { count, isLoading: countLoading } = useCount(user, projectId, query);
  if (fieldsLoading || countLoading) return <Loading />;
  if (!fields || !count) return null;
  const tagFields = fields.filter((f) => f.type === "tag");
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2">
      <div className="flex flex-col gap-3 ">
        <h4>Select options below to update {count} documents</h4>
        {tagFields.length === 0 ? (
          <div>There are no tag fields in this project. Create a tag field in project setup</div>
        ) : (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button className="flex w-max  items-center justify-between gap-3">
                <DynamicIcon type={"tag"} />
                {field || "Select field"}
                <ChevronDown className="h-5 w-5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuRadioGroup value={field} onValueChange={setField}>
                {tagFields.map((f) => (
                  <DropdownMenuRadioItem key={f.name} value={f.name}>
                    {f.name}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        {field == "" ? null : (
          <>
            <br />
            <AddOrRemoveTag user={user} projectId={projectId} query={query} field={field} />
          </>
        )}
      </div>
      <TagGraph user={user} projectId={projectId} query={query} field={field} />
    </div>
  );
}

interface PropsWithField extends Props {
  field: string;
}

function AddOrRemoveTag({ user, projectId, query, field }: PropsWithField) {
  const { data: fields, isLoading: fieldsLoading } = useFields(user, projectId);
  const { data: fieldValues, isLoading: fieldValuesLoading } = useFieldValues(user, projectId, field);
  const [newTag, setNewTag] = useState("");
  const [selectedTag, setSelectedTag] = useState<string>();
  const [createNew, setCreateNew] = useState(false);
  const canOnlyCreate = !fieldValues?.length;
  const tag = createNew || canOnlyCreate ? newTag : selectedTag;
  const tagExists = tag && fieldValues?.includes(tag);
  const { mutateAsync } = useMutateTags(user, projectId);
  if (fieldsLoading || fieldValuesLoading) return <Loading />;
  if (!fields) return null;

  const selectTag = (tag: string) => {
    setCreateNew(false);
    setSelectedTag(tag);
  };
  const createTag = () => {
    setCreateNew(true);
    setSelectedTag(undefined);
  };

  const onSubmit = (action: "add" | "remove") => {
    if (!tag) {
      alert("No tag?");
      return;
    }
    // TODO validate
    mutateAsync({ tag, action, field, query }).then(() => {
      setNewTag("");
      setSelectedTag(undefined);
    });
  };

  const renderExistingTags = () => {
    if (canOnlyCreate) return null;
    return (
      <>
        <DropdownMenuSeparator className={createNew ? "hidden" : ""} />
        <DropdownMenuLabel className="flex items-center gap-2">
          <DynamicIcon type="tag" />
          Existing tags
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup value={selectedTag} onValueChange={selectTag} className="h-52 overflow-auto">
          {fieldValues?.map((tag) => (
            <DropdownMenuRadioItem value={tag} key={tag} className="ml-2">
              <span>{tag}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </>
    );
  };

  const renderTrigger = () => {
    if (createNew || canOnlyCreate) return "new";
    if (tag) return tag;
    return "Create or select tag";
  };

  return (
    <div className="flex flex-col gap-3 ">
      <div className="flex gap-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild disabled={canOnlyCreate}>
            <Button className="flex w-max items-center gap-2">
              <Tag />
              {renderTrigger()}
              <ChevronDown className="h-5 w-5" />{" "}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onClick={createTag} className={` flex items-center gap-2 ${createNew ? "hidden" : ""}`}>
              <Plus />
              Create a new tag
            </DropdownMenuItem>
            {renderExistingTags()}
          </DropdownMenuContent>
        </DropdownMenu>
        <Input
          className={`${createNew || canOnlyCreate ? "" : "hidden"} w-48`}
          placeholder="create new tag"
          value={newTag}
          onChange={(e) => setNewTag(e.target.value)}
        />
      </div>

      <div className={tag ? "" : "hidden"}>
        <div className={`flex gap-3`}>
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

function TagGraph({ user, projectId, query, field }: PropsWithField) {
  const TagGraphOptions: AggregationOptions = {
    axes: [{ name: "tag", field: field }],
    display: "barchart",
    title: "Tags",
  };
  if (!field) return null;
  return (
    <div>
      <h4 className="text-right text-lg font-bold">Number of documents per tag</h4>
      <AggregateResult user={user} projectId={projectId} query={{}} options={TagGraphOptions} />
    </div>
  );
}

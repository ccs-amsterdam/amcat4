import { AggregationOptions, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import AggregateResult from "../Aggregate/AggregateResult";
import { useFields } from "@/api/fields";
import { ChevronDown } from "lucide-react";
import { Loading } from "../ui/loading";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { useState } from "react";
import { DynamicIcon } from "../ui/dynamic-icon";
import { Button } from "../ui/button";
import { useCount } from "@/api/aggregate";
import AddOrRemoveTag from "./AddOrRemoveTag";

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

function TagGraph({ user, projectId, query: _query, field }: PropsWithField) {
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

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AmcatProjectId, AmcatQuery } from "@/interfaces";
import { ChevronUp, Loader, PlusSquareIcon } from "lucide-react";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { AddFilterButton } from "./AddFilterButton";
import { queriesFromString, queriesToString } from "./libQuery";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  updateQuery: (query: AmcatQuery, executeAfter: number | "never") => void;
  debouncing: boolean;
  queryChanged?: boolean;
  children?: React.ReactNode[]; // pass filters as children
  switchAdvanced?: () => void;
}

export default function MultilineQueryForm({
  children,
  user,
  projectId,
  query,
  debouncing,
  queryChanged,
  updateQuery,
  switchAdvanced,
}: Props) {
  if (!projectId) return null;

  function handleKeyDown(event: any) {
    if (event.key === "Enter" && event.ctrlKey) {
      updateQuery(query, 0);
    }
  }

  function submitForm(e: any) {
    e.preventDefault();
    updateQuery(query, 0);
  }

  return (
    <div className="prose grid max-w-none grid-cols-1 gap-3 dark:prose-invert md:grid-cols-[1fr,300px] lg:gap-6">
      <form className="flex w-full flex-auto flex-col p-1">
        <div className="flex h-10 items-center gap-2">
          <div className="flex items-center">
            <b>Query</b>
          </div>
        </div>
        <Textarea
          className="min-h-[100px] flex-auto focus-visible:ring-transparent"
          placeholder={`Enter multiple (labeled) queries:\n\nLabel1 = query1\nLabel2 = query2`}
          onChange={(e) => {
            updateQuery({ ...query, queries: queriesFromString(e.target.value) }, "never");
          }}
          onKeyDown={handleKeyDown}
          value={queriesToString(query?.queries || [], true)}
        />
        <Button className="mt-1 h-8 w-full  border-2" onClick={submitForm} disabled={!queryChanged}>
          <Loader className={`${debouncing ? "" : "invisible"} mr-2 animate-[spin_2000ms_linear_infinite] `} />
          Submit Query <i className="pl-2">(ctrl+Enter)</i>{" "}
        </Button>
      </form>

      <div className="flex  w-full flex-auto flex-col p-1">
        <div className="flex h-10 items-center gap-2">
          <div className="flex gap-2">
            <b>Filters</b>
            <AddFilterButton user={user} projectId={projectId} value={query} onSubmit={(value) => updateQuery(value, 0)}>
              <PlusSquareIcon />
            </AddFilterButton>
          </div>

          <ChevronUp
            role="button"
            onClick={switchAdvanced}
            className="mb-1 ml-auto  h-8 w-8 cursor-pointer select-none p-1"
          />
        </div>

        <div className="Filters flex-auto">{children}</div>
      </div>
    </div>
  );
}

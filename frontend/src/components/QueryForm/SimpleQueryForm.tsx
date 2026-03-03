import { Input } from "@/components/ui/input";
import { AmcatProjectId, AmcatQuery } from "@/interfaces";
import { ChevronsUpDown, Filter, Loader, Search } from "lucide-react";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { Loading } from "../ui/loading";
import { AddFilterButton } from "./AddFilterButton";
import { queriesFromString, queriesToString } from "./libQuery";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  updateQuery: (query: AmcatQuery, executeAfter: number | "never") => void;
  debouncing: boolean;
  children?: React.ReactNode[]; // pass filters as children
  switchAdvanced?: () => void;
}

export default function SimpleQueryForm({
  children,
  user,
  projectId,
  query,
  debouncing,
  updateQuery,
  switchAdvanced,
}: Props) {
  if (!projectId) return <Loading />;

  function handleKeydown(e: any) {
    if (e.key === "Enter") {
      updateQuery(query, 0);
    }
  }

  return (
    <div>
      <div className="flex flex-nowrap items-center gap-1 p-1">
        <div className="relative  w-auto min-w-[50%] flex-auto">
          <Input
            className="pl-10"
            placeholder="search"
            value={queriesToString(query.queries || [], false)}
            onChange={(e) => {
              updateQuery(
                {
                  ...query,
                  queries: queriesFromString(e.target.value),
                },
                1000,
              );
            }}
            onKeyDown={handleKeydown}
          />
          <div className="pointer-events-none absolute bottom-0 left-0 top-0 flex items-center pl-2">
            {debouncing ? <Loader className="animate-[spin_2000ms_linear_infinite]" /> : <Search />}
          </div>
        </div>
        <div className="flex items-center pl-2">
          <AddFilterButton user={user} projectId={projectId} value={query} onSubmit={(value) => updateQuery(value, 0)}>
            <Filter />
          </AddFilterButton>
          <ChevronsUpDown role="button" onClick={switchAdvanced} className="h-8 w-8 cursor-pointer select-none p-1" />
        </div>
      </div>
      <div className="Filters flex flex-wrap items-center justify-start gap-1 p-1">{children}</div>
    </div>
  );
}

import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ChevronsUpDown, Filter } from "lucide-react";
import QueryForm from "@/components/QueryForm/QueryForm";
import { AmcatQuery } from "@/interfaces";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

import { useMyProjectRole } from "@/api/project";
import AggregateResultPanel from "@/components/Aggregate/AggregateResultPanel";
import Summary from "@/components/Summary/Summary";
import { ErrorMsg } from "@/components/ui/error-message";
import { InfoBox } from "@/components/ui/info-box";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Reindex from "@/components/Update/Reindex";
import Update from "@/components/Update/Update";
import { deserializeQuery, serializeQuery } from "@/lib/serialieQuery";
import { useEffect, useState } from "react";
import { parseAsStringEnum, useQueryState } from "nuqs";

enum Tab {
  Summary = "summary",
  Aggregate = "aggregate",
  Copy = "copy",
  Manage = "manage",
}

const TAB_LABELS: Record<Tab, string> = {
  [Tab.Summary]: "Summary",
  [Tab.Aggregate]: "Aggregate",
  [Tab.Copy]: "Copy",
  [Tab.Manage]: "Document actions",
};

type DashboardSearch = {
  tab?: Tab;
  query?: string;
  show_article_id?: string;
};

export const Route = createFileRoute("/projects/$project/dashboard")({
  component: DashboardPage,
  validateSearch: (search: Record<string, unknown>): DashboardSearch => {
    return {
      tab: Object.values(Tab).includes(search.tab as Tab) ? (search.tab as Tab) : Tab.Summary,
      query: search.query as string | undefined,
      show_article_id: search.show_article_id as string | undefined,
    };
  },
});

function DashboardPage() {
  const { project } = Route.useParams();
  const projectId = decodeURI(project);
  const { user } = useAmcatSession();
  const { role: projectRole } = useMyProjectRole(user, projectId);

  const [tab, setTab] = useQueryState("tab", parseAsStringEnum<Tab>(Object.values(Tab)).withDefault(Tab.Summary));
  const [queryState, setQueryState] = useQueryState("query");

  const [query, setQuery] = useState<AmcatQuery>(() => deserializeQuery(queryState));

  useEffect(() => {
    setQueryState(serializeQuery(query));
  }, [query, setQueryState]);

  if (projectRole === "NONE") return <NoAccess />;

  const isWriter = projectRole === "WRITER" || projectRole === "ADMIN";

  return (
    <div>
      <div className={` pb-4 `}>
        <div className="flex flex-col items-center lg:items-start">
          <div className="w-full">
            <QueryForm user={user} projectId={projectId} query={query} setQuery={setQuery} />
          </div>
        </div>
      </div>

      <InfoBox title="Search syntax &amp; filters" defaultOpen={false} storageKey="search-help-open" className="mb-5">
        <div className="flex flex-col gap-5 text-sm">
          You can enter queries here to search through the project. Results will be displayed below this box. You can minimize the box by clicking on the header.
          <section>
            <h4 className="mb-1.5 font-semibold text-foreground">Query syntax</h4>
            <div className="rounded-md bg-primary/10 p-3">
              <div className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5">
                <b className="font-mono text-primary">climate AND policy</b>
                <span>Both terms must appear</span>
                <b className="font-mono text-primary">climate OR weather</b>
                <span>Either term</span>
                <b className="font-mono text-primary">climate NOT gas</b>
                <span>Exclude a term</span>
                <b className="font-mono text-primary">(climate OR weather) AND policy</b>
                <span>Group with parentheses</span>
                <b className="font-mono text-primary">"climate change"</b>
                <span>Exact phrase</span>
                <b className="font-mono text-primary">"climate policy"~5</b>
                <span>Words within 5 positions of each other</span>
                <b className="font-mono text-primary">climat*</b>
                <span>Wildcard (prefix match)</span>
              </div>
            </div>
          </section>
          <section>
            <h4 className="mb-1.5 font-semibold text-foreground">Filters</h4>
            <p>
              Use the <Filter className="inline h-4 w-4" /> button next to the search bar to add field filters. Filters
              narrow results by date range, keyword values, or document IDs, and are combined with your search query
              using AND.
            </p>
            <p>
              The <ChevronsUpDown className="inline h-4 w-4" /> button expands the query bar so it's easier to enter
              multiple queries.
            </p>
          </section>
        </div>
      </InfoBox>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="mt-5 min-h-[500px] w-full px-1">
        <TabsList className="mb-8 overflow-auto text-sm">
          {Object.values(Tab).map((tabValue) => {
            if (tabValue === Tab.Manage && !isWriter) return null;
            return (
              <TabsTrigger key={tabValue} value={tabValue}>
                {TAB_LABELS[tabValue]}
              </TabsTrigger>
            );
          })}
        </TabsList>
        <div className="">
          <TabsContent value={Tab.Summary}>
            <Summary user={user} projectId={projectId} query={query} />
          </TabsContent>
          <TabsContent value={Tab.Aggregate}>
            <AggregateResultPanel user={user} projectId={projectId} query={query} />
          </TabsContent>
          <TabsContent value={Tab.Manage}>
            <Update user={user} projectId={projectId} query={query} />
          </TabsContent>
          <TabsContent value={Tab.Copy}>
            <Reindex user={user} projectId={projectId} query={query} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

function NoAccess() {
  return (
    <ErrorMsg type="Not Allowed">
      <p className="text-center">
        You do not have access to this project. <br />
      </p>
      <br />

      <p className="mx-auto w-96 text-center text-sm">
        See the <b>Access</b> tab in the menu for more information
      </p>
    </ErrorMsg>
  );
}

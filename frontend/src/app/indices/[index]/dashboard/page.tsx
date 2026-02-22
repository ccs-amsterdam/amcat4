"use client";

import QueryForm from "@/components/QueryForm/QueryForm";
import { AmcatQuery } from "@/interfaces";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

import { useMyIndexrole } from "@/api";
import AggregateResultPanel from "@/components/Aggregate/AggregateResultPanel";
import DownloadArticles from "@/components/Articles/DownloadArticles";
import Summary from "@/components/Summary/Summary";
import { ErrorMsg } from "@/components/ui/error-message";
import { Loading } from "@/components/ui/loading";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Reindex from "@/components/Update/Reindex";
import Update from "@/components/Update/Update";
import { deserializeQuery, serializeQuery } from "@/lib/serialieQuery";
import { parseAsStringEnum, useQueryState } from "nuqs";
import { useEffect, useState, use } from "react";

interface Props {
  params: Promise<{ index: string }>;
}

enum Tab {
  Summary = "summary",
  Aggregate = "aggregate",
  Copy = "copy",
  Update = "update",
  Download = "download",
}

export default function Index(props: Props) {
  const params = use(props.params);
  const indexId = decodeURI(params.index);
  const { user } = useAmcatSession();
  const indexRole = useMyIndexrole(user, indexId);
  const [tab, setTab] = useQueryState("tab", parseAsStringEnum<Tab>(Object.values(Tab)).withDefault(Tab.Summary));
  const [queryState, setQueryState] = useQueryState("query");
  const [query, setQuery] = useState<AmcatQuery>(() => deserializeQuery(queryState));

  useEffect(() => {
    // when query is edited, store it compressed in the URL (if it's not too long).
    // This allows sharing URLs with queries for most queries.
    setQueryState(serializeQuery(query));
  }, [query]);

  if (indexRole === "NONE") return <NoAccess />;

  const isWriter = indexRole === "WRITER" || indexRole === "ADMIN";

  return (
    <div>
      <div className={` pb-4 `}>
        <div className="flex flex-col items-center lg:items-start">
          <div className="w-full">
            <QueryForm user={user} indexId={indexId} query={query} setQuery={setQuery} />
          </div>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="mt-5 min-h-[500px] w-full px-1">
        <TabsList className="mb-8 overflow-auto text-sm">
          {Object.keys(Tab).map((tab) => {
            if (tab === "Update" && !isWriter) return null;
            const tabValue = Tab[tab as keyof typeof Tab];
            return (
              <TabsTrigger key={tabValue} value={tabValue}>
                {tab}
              </TabsTrigger>
            );
          })}
        </TabsList>
        <div className="">
          <TabsContent value={Tab.Summary}>
            <Summary user={user} indexId={indexId} query={query} />
          </TabsContent>
          <TabsContent value={Tab.Aggregate}>
            <AggregateResultPanel user={user} indexId={indexId} query={query} />
          </TabsContent>
          <TabsContent value={Tab.Update}>
            <Update user={user} indexId={indexId} query={query} />
          </TabsContent>
          <TabsContent value={Tab.Copy}>
            <Reindex user={user} indexId={indexId} query={query} />
          </TabsContent>
          <TabsContent value={Tab.Download}>
            <DownloadArticles user={user} indexId={indexId} query={query} />
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
        You do not have access to this index. <br />
      </p>
      <br />

      <p className="mx-auto w-96 text-center text-sm">
        See the <b>Access</b> tab in the menu for more information
      </p>
    </ErrorMsg>
  );
}

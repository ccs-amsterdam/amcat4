import { createFileRoute, useNavigate } from "@tanstack/react-router";

import { useAmcatConfig } from "@/api/config";
import { useIndex } from "@/api/index";
import Multimedia from "@/components/Multimedia/Multimedia";
import Upload from "@/components/Upload/Upload";
import { ErrorMsg } from "@/components/ui/error-message";
import { Loading } from "@/components/ui/loading";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TabsContent } from "@radix-ui/react-tabs";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { parseAsStringEnum, useQueryState } from "nuqs";

enum Tab {
  Upload = "upload",
  Multimedia = "multimedia",
  // Preprocessing = "preprocessing",
}

type DataSearch = {
  tab?: Tab;
};

export const Route = createFileRoute("/projects/$project/data")({
  component: DataPage,
  validateSearch: (search: Record<string, unknown>): DataSearch => {
    return {
      tab: Object.values(Tab).includes(search.tab as Tab) ? (search.tab as Tab) : Tab.Upload,
    };
  },
});

function DataPage() {
  const { project } = Route.useParams();

  const { user } = useAmcatSession();
  const { data: serverConfig, isLoading: configLoading } = useAmcatConfig();
  const indexId = decodeURI(project);
  const { data: index, isLoading: loadingIndex } = useIndex(user, indexId);

  const [tab, setTab] = useQueryState("tab", parseAsStringEnum<Tab>(Object.values(Tab)).withDefault(Tab.Upload));

  if (loadingIndex || configLoading) return <Loading />;
  if (!index) return <ErrorMsg type="Not Allowed">Need to be logged in</ErrorMsg>;

  return (
    <div className="flex w-full  flex-col gap-10">
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="flex min-h-[500px] w-full flex-col">
        <TabsList className="mb-12 overflow-x-auto">
          {Object.keys(Tab).map((tab) => {
            const disabled = tab === "Multimedia" && !serverConfig?.minio;
            const tabValue = Tab[tab as keyof typeof Tab];
            return (
              <TabsTrigger key={tabValue} value={tabValue} disabled={disabled}>
                {tab}
              </TabsTrigger>
            );
          })}
        </TabsList>
        <div className="mx-auto w-full ">
          <TabsContent value={Tab.Upload}>
            <Upload indexId={index.id} user={user} />
          </TabsContent>
          <TabsContent value={Tab.Multimedia}>
            <Multimedia indexId={index.id} user={user} />
          </TabsContent>
          {/*<TabsContent value={Tab.Preprocessing}>
            <Preprocessing indexId={index.id} user={user} />
          </TabsContent>*/}
        </div>
      </Tabs>
    </div>
  );
}

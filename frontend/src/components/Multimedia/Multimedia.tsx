import { useMultimediaList } from "@/api/multimedia";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { Loading } from "../ui/loading";
import MultimediaUpload from "./MultimediaUpload";
import { MultimediaListItem } from "@/interfaces";
import { useMemo, useState } from "react";
import { Button } from "../ui/button";
import { ChevronDown, ChevronLeft, ChevronRight, Dot, LayoutGrid, List, Undo2 } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../ui/dropdown-menu";
import RenderMultimedia from "./RenderMultimedia";

interface Props {
  projectId: string;
  user: AmcatSessionUser;
}

export default function Multimedia({ projectId, user }: Props) {
  const [prefix, setPrefix] = useState<string>("");
  const [page, setPage] = useState(0);
  const [format, setFormat] = useState<"list" | "panes">("list");

  const { data: multimediaList, isLoading: loadingMultimediaList } = useMultimediaList(user, projectId, { prefix });

  const items = multimediaList?.filter((item) => !item.is_dir) || [];
  const pageSize = format === "list" ? 20 : 4;
  const showItems = items.slice(page * pageSize, page * pageSize + pageSize);

  function renderItems() {
    if (format === "list") {
      return showItems?.map((item) => (
        <div key={item.key} className="flex items-center gap-2">
          <Dot className="h-4 w-4" />
          <span title={item.key} className="overflow-hidden text-ellipsis whitespace-nowrap">
            {item.key}
          </span>
        </div>
      ));
    }

    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {showItems?.map((item) => {
          return <RenderMultimedia user={user} projectId={projectId} url={item.key} height={240} />;
        })}
      </div>
    );
  }

  return (
    <div className="prose flex max-w-none flex-wrap-reverse dark:prose-invert">
      <div className="flex w-full max-w-none  flex-col gap-3 p-3 xl:max-w-[60%]">
        <h3 className="mt-0">Multimedia list</h3>
        {loadingMultimediaList ? <Loading /> : null}
        <div className="min-h-[4rem]">
          <DirectoryBrowser projectId={projectId} prefix={prefix} setPrefix={setPrefix} multimediaList={multimediaList} />
        </div>
        <div className={` flex items-center justify-between ${showItems.length ? "" : "hidden"} `}>
          <div className="flex items-center ">
            <Button
              className="px-1 disabled:text-secondary"
              variant="ghost"
              onClick={() => setFormat("list")}
              disabled={format === "list"}
            >
              <List className={` h-8 w-8`} />
            </Button>
            <Button
              className="px-1 disabled:text-secondary"
              variant="ghost"
              onClick={() => setFormat("panes")}
              disabled={format === "panes"}
            >
              <LayoutGrid className="h-7 w-7" />
            </Button>
          </div>
          <div className="text-sm text-gray-500">
            <ItemPagination page={page} setPage={setPage} items={items} pageSize={pageSize} />
          </div>
        </div>

        {renderItems()}
      </div>
      <div className="w-full lg:w-1/2  xl:w-[40%]">
        <div className="flex min-h-[20rem] flex-col gap-3 p-3 pl-6">
          <h3 className="mt-0">Upload multimedia</h3>
          <MultimediaUpload projectId={projectId} user={user} />
        </div>
      </div>
    </div>
  );
}

function ItemPagination({
  page,
  setPage,
  items,
  pageSize,
}: {
  page: number;
  setPage: (page: number) => void;
  items: MultimediaListItem[];
  pageSize: number;
}) {
  return (
    <div className="flex select-none items-center justify-between gap-3">
      <h3 className="m-0 text-secondary">
        {items.length} file{items.length === 1 ? "" : "s"}
      </h3>
      <div className={` flex gap-2 ${items.length <= pageSize ? "hidden" : ""} `}>
        <Button
          variant="secondary"
          onClick={() => setPage(Math.max(page - 1, 0))}
          disabled={page === 0}
          className="h-8 p-1"
        >
          <ChevronLeft />
        </Button>
        <Button
          variant="secondary"
          onClick={() => setPage(Math.min(page + 1, Math.floor(items.length / pageSize)))}
          disabled={page + 1 >= Math.floor(items.length / pageSize)}
          className="h-8 p-1"
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

function DirectoryBrowser({
  projectId,
  prefix,
  setPrefix,
  multimediaList,
}: {
  projectId: string;
  prefix: string;
  setPrefix: (prefix: string) => void;
  multimediaList?: MultimediaListItem[];
}) {
  const path = useMemo(() => {
    if (!prefix) return [];
    const split = prefix.split("/");
    return split.slice(0, split.length - 1);
  }, [projectId, prefix]);

  const directories = useMemo(() => {
    if (!multimediaList) return [];
    return multimediaList
      .filter((item) => item.is_dir)
      .map((item) => {
        // get second to last split of /, because this is the next path name
        const split = item.key.split("/");
        return split[split.length - 2];
      });
  }, [multimediaList]);

  function selectPath(i: number) {
    setPrefix(path.slice(0, i + 1).join("/") + "/");
  }

  return (
    <div className="">
      <div className="flex items-center">
        <Button variant="link" className="px-3 py-1 text-lg" onClick={() => setPrefix("")}>
          {path.length > 0 ? <Undo2 className="h-6 w-6" /> : null}
        </Button>

        {path.map((dir, i) => {
          const current = i === path.length - 1;
          return (
            <Button
              key={dir}
              className={`px-1 text-lg ${current ? " disabled:text-primary" : ""}`}
              variant="ghost"
              onClick={() => selectPath(i)}
              disabled={current}
            >
              {i === 0 ? "" : "/ "}
              {dir}
            </Button>
          );
        })}
        <DropdownMenu>
          <DropdownMenuTrigger asChild className={directories.length ? "" : "hidden"}>
            <Button variant="ghost" className="gap-1 px-1 text-lg font-bold text-secondary">
              {path.length ? " / " : ""} {directories.length} director{directories.length === 1 ? "y" : "ies"}
              <ChevronDown className="h-5 w-5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <div className="flex flex-col gap-1">
              {directories.map((dir) => (
                <DropdownMenuItem onClick={() => setPrefix(`${prefix}${dir}/`)} key={dir}>
                  {dir}
                </DropdownMenuItem>
              ))}
            </div>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

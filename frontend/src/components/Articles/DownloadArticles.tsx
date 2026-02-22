import { useMyIndexrole } from "@/api";
import { useFields } from "@/api/fields";
import { AmcatField, AmcatIndexId, AmcatQuery, AmcatUserRole } from "@/interfaces";
import { ChevronDown, Download, EyeOff } from "lucide-react";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { MouseEvent, useEffect, useState } from "react";
import { useCSVDownloader } from "react-papaparse";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import { Dialog, DialogContent } from "../ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../ui/dropdown-menu";
import { Loading } from "../ui/loading";
import { Progress } from "../ui/progress";
import ArticleTable from "./ArticleTable";
import usePaginatedArticles from "./usePaginatedArticles";

import { Input } from "../ui/input";

interface Props {
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  query: AmcatQuery;
}

export default function DownloadArticles({ user, indexId, query }: Props) {
  const [fields, setFields] = useState<AmcatField[] | undefined>();

  const { role: indexRole } = useMyIndexrole(user, indexId);
  const { data: allFields, isLoading } = useFields(user, indexId);

  useEffect(() => {
    if (!allFields) return;
    setFields(
      allFields.filter((field) => {
        if (!field.client_settings.inList) return false;
        if (indexRole === "METAREADER" && field.metareader.access === "none") return false;
        return true;
      }),
    );
  }, [indexRole, allFields]);

  function toggleField(e: MouseEvent, field: AmcatField) {
    e.preventDefault();
    if (!fields) return;
    if (fields.find((f) => f.name === field.name)) {
      setFields(fields.filter((f) => f !== field));
    } else {
      setFields([...fields, field]);
    }
  }

  if (isLoading) return <Loading />;
  if (!indexRole || !fields) return null;

  return (
    <ArticleTable user={user} indexId={indexId} query={query} fields={fields}>
      <div className="flex justify-end gap-3 ">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="flex items-center gap-2">
              {fields.length} fields <ChevronDown className="h-5 w-5" />{" "}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent onClick={(e) => e.preventDefault()} className="max-h-60 overflow-auto">
            {allFields?.map((field) => {
              const selected = fields.find((f) => f.name === field.name);
              const forbidden = indexRole === "METAREADER" && field.metareader.access === "none";
              const snippet = indexRole === "METAREADER" && field.metareader.access === "snippet";
              return (
                <DropdownMenuItem
                  disabled={forbidden}
                  onClick={(e) => toggleField(e, field)}
                  key={field.name}
                  className="flex gap-2"
                >
                  {selected ? <Checkbox checked={true} /> : <Checkbox checked={false} />}
                  {field.name}
                  <span className="text-destructive">{forbidden ? <EyeOff className="h-4 w-4" /> : ""}</span>
                  <span className="text-foreground/50">{snippet ? "(snippet)" : ""}</span>
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
        <Downloader user={user} indexId={indexId} query={query} fields={fields} indexRole={indexRole} />
      </div>
    </ArticleTable>
  );
}

interface DownloaderProps {
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  query: AmcatQuery;
  fields: AmcatField[];
  indexRole: AmcatUserRole;
}

function Downloader({ user, indexId, query, fields, indexRole }: DownloaderProps) {
  const [enabled, setEnabled] = useState(false);
  const [filename, setFilename] = useState<string>("");
  const { CSVDownloader, Type } = useCSVDownloader();
  const { articles, pageIndex, pageCount, isLoading, nextPage } = usePaginatedArticles({
    user,
    indexId,
    query,
    fields,
    indexRole,
    pageSize: 200,
    combineResults: true,
    enabled,
  });

  const defaultFilename = `${indexId}_articles`;

  useEffect(() => {
    if (pageIndex < pageCount - 1) nextPage();
  }, [nextPage, pageIndex, pageCount]);

  if (!enabled)
    return (
      <Button onClick={() => setEnabled(true)} className="flex items-center gap-2">
        <Download className="h-5 w-5" />
      </Button>
    );

  function render() {
    if (isLoading || pageIndex < pageCount - 1)
      return (
        <div className=" ">
          <div className="mb-1 flex justify-between">
            <div>Fetching pages</div>
            <div className={pageCount ? "" : "hidden"}>
              {pageIndex + 1} / {pageCount}
            </div>
          </div>
          <Progress className="mt-2" value={(100 * pageIndex) / pageCount - 1} />
        </div>
      );

    return (
      <>
        <div className="flex-between flex items-center gap-1">
          <Input
            placeholder={defaultFilename}
            className="selection:bg-foreground/20 focus-visible:ring-transparent"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
          />
          <div className="text-foreground/70">.csv</div>
        </div>

        <div onClick={() => setEnabled(false)}>
          <CSVDownloader
            type={Type.Button}
            className="w-full rounded-md border bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/80"
            download={true}
            data={articles}
            bom={true}
            filename={`${filename || defaultFilename}`}
          >
            Download
          </CSVDownloader>
        </div>
      </>
    );
  }

  return (
    <Dialog open={true} onOpenChange={(open) => setEnabled(open)}>
      <DialogContent>
        <div className="mt-5 flex flex-col gap-3">{render()}</div>
      </DialogContent>
    </Dialog>
  );
}

import { useMyProjectRole } from "@/api/project";
import { AmcatField, AmcatProjectId, AmcatQuery, AmcatUserRole } from "@/interfaces";
import { Download } from "lucide-react";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Dialog, DialogContent } from "../ui/dialog";
import { Progress } from "../ui/progress";
import usePaginatedArticles from "./usePaginatedArticles";

import { Input } from "../ui/input";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  fields: AmcatField[];
}

export default function DownloadArticles({ user, projectId, query, fields }: Props) {
  const { role: projectRole } = useMyProjectRole(user, projectId);

  if (!projectRole) return null;

  return <Downloader user={user} projectId={projectId} query={query} fields={fields} projectRole={projectRole} />;
}

interface DownloaderProps {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  fields: AmcatField[];
  projectRole: AmcatUserRole;
}

function Downloader({ user, projectId, query, fields, projectRole }: DownloaderProps) {
  const [enabled, setEnabled] = useState(false);
  const [filename, setFilename] = useState<string>("");
  const [isProcessing, setIsProcessing] = useState(false); // Track the CSV conversion step

  const { articles, pageIndex, pageCount, isLoading, nextPage } = usePaginatedArticles({
    user,
    projectId,
    query,
    fields,
    projectRole,
    pageSize: 200,
    combineResults: true,
    enabled,
  });

  const defaultFilename = `${projectId}_articles`;

  useEffect(() => {
    if (pageIndex < pageCount - 1) nextPage();
  }, [nextPage, pageIndex, pageCount]);

  // The actual download logic
  const handleDownload = async () => {
    setIsProcessing(true);
    try {
      const Papa = (await import("papaparse")).default;
      const csv = Papa.unparse(articles);

      const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `${filename || defaultFilename}.csv`);
      document.body.appendChild(link);
      link.click();

      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      // Close the dialog after success
      setEnabled(false);
    } catch (error) {
      console.error("CSV generation failed", error);
    } finally {
      setIsProcessing(false);
    }
  };

  if (!enabled)
    return (
      <Button onClick={() => setEnabled(true)} className="flex items-center gap-2">
        <Download className="h-5 w-5" />
        Download
      </Button>
    );

  function renderContent() {
    const isFetching = isLoading || pageIndex < pageCount - 1;

    if (isFetching)
      return (
        <div>
          <div className="mb-1 flex justify-between">
            <div>Fetching pages</div>
            <div className={pageCount ? "" : "hidden"}>
              {pageIndex + 1} / {pageCount}
            </div>
          </div>
          <Progress className="mt-2" value={(100 * pageIndex) / (pageCount - 1 || 1)} />
        </div>
      );

    return (
      <>
        <div className="flex items-center gap-1">
          <Input
            placeholder={defaultFilename}
            className="selection:bg-foreground/20 focus-visible:ring-transparent"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
          />
          <div className="text-foreground/70">.csv</div>
        </div>

        <Button onClick={handleDownload} disabled={isProcessing} className="w-full">
          {isProcessing ? "Preparing file..." : "Download"}
        </Button>
      </>
    );
  }

  return (
    <Dialog open={true} onOpenChange={(open) => setEnabled(open)}>
      <DialogContent>
        <div className="mt-5 flex flex-col gap-3">{renderContent()}</div>
      </DialogContent>
    </Dialog>
  );
}

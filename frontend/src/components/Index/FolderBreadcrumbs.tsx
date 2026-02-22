import { Button } from "@/components/ui/button";
import { Folder, FolderOpen } from "lucide-react";
import { Fragment } from "react";
import { Breadcrumb, BreadcrumbItem, BreadcrumbList } from "../ui/breadcrumb";

export function FolderBreadcrumbs({
  currentPath,
  toFolder,
}: {
  currentPath: string | null;
  toFolder: (folder: string | null) => void;
}) {
  const pathArray = currentPath ? currentPath.split("/").filter((p) => p) : [];
  // if (pathArray.length == 0) return null;

  return (
    <Breadcrumb>
      <BreadcrumbList className="gap-0 pl-0  sm:gap-0 ">
        <BreadcrumbItem>
          <Button
            disabled={pathArray.length === 0}
            className="h-7 px-1 text-base"
            variant="ghost"
            onClick={() => toFolder(null)}
          >
            {/*<FolderOpen className="inline h-5 w-5" />*/}
            Indices
          </Button>
        </BreadcrumbItem>
        {pathArray.map((folder, i) => (
          <Fragment key={i + folder}>
            <div className="mx-1 text-foreground/20">/</div>
            <BreadcrumbItem>
              <Button
                className="h-7  overflow-hidden text-ellipsis text-nowrap px-1"
                variant="ghost"
                onClick={() => toFolder(pathArray.slice(0, i + 1).join("/"))}
              >
                {folder || "Root"}
              </Button>
            </BreadcrumbItem>
          </Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/projects/")({
  component: ProjectsPage,
});

import { useAmcatConfig } from "@/api/config";
import { SelectProject } from "@/components/Project/SelectProject";
import { Loading } from "@/components/ui/loading";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

function ProjectsPage() {
  const { data: serverConfig, isLoading } = useAmcatConfig();
  if (isLoading) return <Loading />;
  if (!serverConfig) return <div className="p-3">Could not load server configuration</div>;

  return (
    <div className="h-full w-full max-w-7xl animate-fade-in px-0 dark:prose-invert md:px-4">
      <div className="mt-[4vh]">
        <SelectProject />
      </div>
    </div>
  );
}

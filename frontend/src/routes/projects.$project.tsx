import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/projects/$project")({
  component: ProjectLayout,
});

import { ErrorMsg } from "@/components/ui/error-message";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useMyProjectRole } from "@/api/project";
import { Loading } from "@/components/ui/loading";

function ProjectLayout() {
  const { project } = Route.useParams();
  const { user } = useAmcatSession();
  const { role: projectRole, isLoading } = useMyProjectRole(user, project);

  if (isLoading) return <Loading />;
  if (!projectRole) return <NoAccessToThisProject />;

  return <Outlet />;
}

function NoAccessToThisProject() {
  return (
    <ErrorMsg type="No access">
      <p className="w-[500px] max-w-[95vw] text-center">You do not have access to this project</p>
    </ErrorMsg>
  );
}

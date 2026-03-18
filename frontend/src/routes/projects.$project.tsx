import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/projects/$project")({
  component: ProjectLayout,
});

import { ErrorMsg } from "@/components/ui/error-message";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useMyProjectRole, useProject } from "@/api/project";
import { Loading } from "@/components/ui/loading";

function ProjectLayout() {
  const { project } = Route.useParams();
  const { user } = useAmcatSession();
  const { role: projectRole, isLoading } = useMyProjectRole(user, project);
  const { error } = useProject(user, project);

  if (isLoading) return <Loading />;
  if (error) return <CouldNotOpenProject message={(error as Error).message} />;
  if (!projectRole) return <NoAccessToThisProject />;

  return <Outlet />;
}

function CouldNotOpenProject({ message }: { message: string }) {
  return (
    <ErrorMsg type="Could not open project">
      <p className="w-[500px] max-w-[95vw] text-center">{message}</p>
    </ErrorMsg>
  );
}

function NoAccessToThisProject() {
  return (
    <ErrorMsg type="No access">
      <p className="w-[500px] max-w-[95vw] text-center">You do not have access to this project</p>
    </ErrorMsg>
  );
}

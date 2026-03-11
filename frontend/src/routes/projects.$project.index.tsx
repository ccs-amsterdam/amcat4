import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useMyProjectRole } from "@/api/project";
import { hasMinAmcatRole } from "@/lib/utils";
import { Loading } from "@/components/ui/loading";

export const Route = createFileRoute("/projects/$project/")({
  component: ProjectIndex,
});

function ProjectIndex() {
  const { project } = Route.useParams();
  const projectId = decodeURI(project);
  const { user } = useAmcatSession();
  const { role, isLoading } = useMyProjectRole(user, projectId);
  const navigate = useNavigate();

  useEffect(() => {
    if (isLoading || !role) return;
    const tab = hasMinAmcatRole(role, "METAREADER") ? "dashboard" : "settings";
    navigate({ to: `/projects/$project/${tab}`, params: { project }, replace: true });
  }, [role, isLoading, project, navigate]);

  return <Loading />;
}

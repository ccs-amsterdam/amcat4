import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef } from "react";

const EMPTY_QUERY = {};
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useMyProjectRole } from "@/api/project";
import { useArticles } from "@/api/articles";
import { hasMinAmcatRole } from "@/lib/utils";
import { Loading } from "@/components/ui/loading";
import { EmptyProject } from "@/components/Summary/Summary";

export const Route = createFileRoute("/projects/$project/")({
  component: ProjectIndex,
});

function ProjectIndex() {
  const { project } = Route.useParams();
  const projectId = decodeURI(project);
  const { user } = useAmcatSession();
  const { role, isLoading: roleLoading } = useMyProjectRole(user, projectId);
  const { data: articleData, isLoading: articlesLoading } = useArticles(
    user,
    projectId,
    EMPTY_QUERY,
    undefined,
    undefined,
    hasMinAmcatRole(role, "METAREADER"),
  );
  const navigate = useNavigate();
  const navigated = useRef(false);

  const isEmpty = articleData?.pages[0]?.meta?.total_count === 0;

  useEffect(() => {
    if (navigated.current || roleLoading || !role) return;
    if (!hasMinAmcatRole(role, "METAREADER")) {
      navigated.current = true;
      navigate({ to: `/projects/$project/settings`, params: { project }, replace: true });
      return;
    }
    if (articlesLoading || articleData == null) return;
    if (!isEmpty) {
      navigated.current = true;
      navigate({ to: `/projects/$project/dashboard`, params: { project }, replace: true });
    }
  }, [role, roleLoading, project, navigate, isEmpty, articlesLoading, articleData]);

  if (roleLoading || !role) return <Loading />;
  if (!hasMinAmcatRole(role, "METAREADER")) return <Loading />;
  if (articlesLoading || articleData == null) return <Loading />;
  if (!isEmpty) return <Loading />;

  return <EmptyProject projectId={projectId} role={role} />;
}

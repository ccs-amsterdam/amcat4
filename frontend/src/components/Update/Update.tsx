import { AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useFields } from "@/api/fields";
import Tags from "./Tags";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
}

export default function Update({ user, projectId, query }: Props) {
  const { data: fields } = useFields(user, projectId);
  if (!fields) return null;

  return (
    <div>
      <Tags user={user} projectId={projectId} query={query} />
    </div>
  );
}

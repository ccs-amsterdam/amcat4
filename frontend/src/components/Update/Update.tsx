import { AmcatIndexId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useFields } from "@/api/fields";
import Tags from "./Tags";

interface Props {
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  query: AmcatQuery;
}

export default function Update({ user, indexId, query }: Props) {
  const { data: fields } = useFields(user, indexId);
  if (!fields) return null;

  return (
    <div>
      <Tags user={user} indexId={indexId} query={query} />
    </div>
  );
}

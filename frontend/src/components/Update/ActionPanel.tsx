import { AmcatField, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useHasProjectRole } from "@/api/project";
import { Loading } from "../ui/loading";
import { InfoBox } from "../ui/info-box";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import UpdateField from "./UpdateField";
import DeleteDocuments from "./DeleteDocuments";
import DownloadArticles from "../Articles/DownloadArticles";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  onDeleteSuccess?: () => void;
  displayFields: AmcatField[];
}

export default function ActionPanel({ user, projectId, query, onDeleteSuccess, displayFields }: Props) {
  const isAdmin = useHasProjectRole(user, projectId, "ADMIN");

  if (isAdmin === undefined) return <Loading />;

  if (!isAdmin) {
    return (
      <InfoBox title="Admin role required">
        You need ADMIN role to perform update and delete operations on this project.
      </InfoBox>
    );
  }

  return (
    <Tabs defaultValue="update">
      <TabsList className="mb-4">
        <TabsTrigger value="update">Update field</TabsTrigger>
        <TabsTrigger value="delete">Delete documents</TabsTrigger>
        <TabsTrigger value="download">Download</TabsTrigger>
      </TabsList>
      <TabsContent value="update">
        <UpdateField user={user} projectId={projectId} query={query} />
      </TabsContent>
      <TabsContent value="delete">
        <DeleteDocuments user={user} projectId={projectId} query={query} onSuccess={onDeleteSuccess} />
      </TabsContent>
      <TabsContent value="download">
        <DownloadArticles user={user} projectId={projectId} query={query} fields={displayFields} />
      </TabsContent>
    </Tabs>
  );
}

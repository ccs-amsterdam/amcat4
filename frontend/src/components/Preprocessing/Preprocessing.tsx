import { AmcatProjectId } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import PreprocessingTasks from "./PreprocessingTasks";
import PreprocessingInstructions from "./PreprocessingInstructions";

interface Props {
  projectId: AmcatProjectId;
  user: AmcatSessionUser;
}

export default function Preprocessing({ projectId, user }: Props) {
  return (
    <div className="grid grid-cols-1 p-3 lg:grid-cols-2">
      <PreprocessingTasks projectId={projectId} user={user} />
      <PreprocessingInstructions projectId={projectId} user={user} />
    </div>
  );
}

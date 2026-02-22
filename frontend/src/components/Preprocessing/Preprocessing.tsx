import { AmcatIndexId } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import PreprocessingTasks from "./PreprocessingTasks";
import PreprocessingInstructions from "./PreprocessingInstructions";

interface Props {
  indexId: AmcatIndexId;
  user: AmcatSessionUser;
}

export default function Preprocessing({ indexId, user }: Props) {
  return (
    <div className="grid grid-cols-1 p-3 lg:grid-cols-2">
      <PreprocessingTasks indexId={indexId} user={user} />
      <PreprocessingInstructions indexId={indexId} user={user} />
    </div>
  );
}

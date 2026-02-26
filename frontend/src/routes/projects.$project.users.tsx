import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/projects/$project/users")({
  component: UsersPage,
});

import { useAmcatConfig } from "@/api/config";
import { useProject, useMutateProject } from "@/api/project";
import { useProjectUsers, useMutateProjectUser } from "@/api/projectUsers";
import UserRoleTable from "@/components/Users/UserRoleTable";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ErrorMsg } from "@/components/ui/error-message";
import { Loading } from "@/components/ui/loading";
import { AmcatProject, AmcatUserRole } from "@/interfaces";
import { Edit } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

const roles = ["METAREADER", "READER", "WRITER", "ADMIN"];

function UsersPage() {
  const { project } = Route.useParams();
  const { user } = useAmcatSession();
  const projectId = decodeURI(project);
  const { data: projectData, isLoading: loadingProject } = useProject(user, projectId);

  if (loadingProject) return <Loading />;
  if (!projectData) return <ErrorMsg type="Not Allowed">Need to be logged in</ErrorMsg>;

  return (
    <div className="flex w-full  flex-col gap-10">
      <Users project={projectData} />
    </div>
  );
}

function Users({ project }: { project: AmcatProject }) {
  const { user } = useAmcatSession();
  const { data: users, isLoading: loadingUsers } = useProjectUsers(user, project.id);
  const { mutateAsync } = useMutateProjectUser(user, project.id);
  const { mutate: mutateProject } = useMutateProject(user);
  const { data: config } = useAmcatConfig();

  if (loadingUsers) return <Loading />;

  const ownRole = config?.authorization === "no_auth" ? "ADMIN" : project?.user_role;

  async function changeRole(email: string | undefined, role: string, action: "create" | "delete" | "update") {
    mutateAsync({ email, role, action }).catch(console.error);
  }

  if (!user || !ownRole || !users || !changeRole) return <ErrorMsg type="Not Allowed">Need to be logged in</ErrorMsg>;

  return (
    <div className="grid grid-cols-1 gap-6 p-3 lg:grid-cols-[1fr,19rem]">
      <div className="w-full max-w-4xl">
        <UserRoleTable user={user} ownRole={ownRole} users={users} changeRole={changeRole} roles={roles} />
      </div>
      <div className="ml-auto flex h-max items-center gap-5 ">
        <h3 className="text-xl">Guest role</h3>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button className="flex gap-3">
              <div>{project.guest_role}</div>
              <Edit className="h-5 w-5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <div className="flex flex-col gap-2">
              {["NONE", "METAREADER", "READER", "WRITER"].map((role) => (
                <DropdownMenuItem
                  key={role}
                  onClick={() => {
                    mutateProject({ id: project.id, guest_role: role as AmcatUserRole });
                  }}
                >
                  {role}
                </DropdownMenuItem>
              ))}
            </div>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

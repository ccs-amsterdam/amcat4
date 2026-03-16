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
import { InfoBox } from "@/components/ui/info-box";

const roles = ["OBSERVER", "METAREADER", "READER", "WRITER", "ADMIN"];

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
    <div className="flex flex-col gap-6 p-3">
      <div className="w-full max-w-4xl">
        <GuestRoleSelector project={project} mutateProject={mutateProject} />
        <UserRoleTable user={user} ownRole={ownRole} users={users} changeRole={changeRole} roles={roles} projectId={project.id} />
      </div>
      <ProjectUserInstructions />
    </div>
  );
}

function GuestRoleSelector({
  project,
  mutateProject,
}: {
  project: AmcatProject;
  mutateProject: (data: { id: string; guest_role: AmcatUserRole }) => void;
}) {
  return (
    <div className="mb-4 flex items-center gap-3">
      <h3 className="text-base font-semibold">Guest role</h3>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="flex gap-3">
            <div>{project.guest_role ?? "NONE"}</div>
            <Edit className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <div className="flex flex-col gap-2">
            {["NONE", "OBSERVER", "METAREADER", "READER", "WRITER"].map((role) => (
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
  );
}

function ProjectUserInstructions() {
  return (
    <InfoBox title="Information on user management" storageKey="infobox:project-users" className="max-w-4xl">
      <div className="flex flex-col gap-5 text-sm">
        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Project roles</h4>
          <p className="mb-2">Every project has its own users table with the following roles and incremental permissions.</p>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[6rem_1fr] gap-3">
              <b className="text-primary">OBSERVER</b>
              Can find the project and see project metadata, but cannot search documents.
              <b className="text-primary">METAREADER</b>
              Can also search documents, but only view document metadata. Project ADMINs can determine which fields are considered metadata.
              <b className="text-primary">READER</b>
              Can view all document data.
              <b className="text-primary">WRITER</b>
              Can upload and edit documents.
              <b className="text-primary">ADMIN</b>
              Can manage users, edit project settings and break things.
            </div>
          </div>
          <p className="mt-2">
            Project roles (except ADMIN) can also be given to any email address on a given domain, like <b>*@my-university.com</b>.
          </p>
        </section>

        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Guest role</h4>
          <p className="mb-2">
            The guest role determines what anyone can see in this project — even without a personal user account.
            Depending on the server's authorization policy, this can include completely anonymous visitors.
          </p>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[6rem_1fr] gap-3">
              <b className="text-primary">NONE</b>
              Guests cannot access the project at all. Only users with an explicit project role can see it.
              <b className="text-primary">OBSERVER</b>
              Guests can find the project and see project metadata, but cannot search documents.
              <b className="text-primary">METAREADER</b>
              Guests can find the project and search documents, but only see document metadata. Project ADMINs control which fields count as metadata.
              <b className="text-primary">READER</b>
              Guests can view all document data. Use this to make a project fully public.
              <b className="text-primary">WRITER</b>
              Guests can upload and edit documents. Only recommended for controlled, private environments.
            </div>
          </div>
          <p className="mt-2">
            The guest role is the easiest way to share public data. Whether anonymous visitors are allowed depends on the server's <b>authorization policy</b> — ask your server admin if you're unsure.
          </p>
        </section>
      </div>
    </InfoBox>
  );
}

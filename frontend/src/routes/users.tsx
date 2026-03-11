import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/users")({
  component: Users,
});

import { useAmcatBranding } from "@/api/branding";
import { useAmcatConfig } from "@/api/config";
import { useCurrentUserDetails } from "@/api/userDetails";
import { useMutateUser, useUsers } from "@/api/users";
import { AmcatSessionUser, useAmcatSession } from "@/components/Contexts/AuthProvider";
import { Loading } from "@/components/ui/loading";
import UserRoleTable from "@/components/Users/UserRoleTable";
import { InfoBox } from "@/components/ui/info-box";

import { AmcatBranding, AmcatConfig } from "@/interfaces";

const roles = ["WRITER", "ADMIN"];

function Users() {
  const { user } = useAmcatSession();
  const { data: serverConfig, isLoading: configLoading } = useAmcatConfig();
  const { data: serverBranding, isLoading: brandingLoading } = useAmcatBranding();
  if (configLoading || brandingLoading) return <Loading />;

  return (
    <div className="mx-auto mt-12 w-full max-w-7xl px-6 py-6">
      <ServerSettings user={user} serverConfig={serverConfig!} serverBranding={serverBranding!} />
    </div>
  );
}

interface ServerSettingsProps {
  user: AmcatSessionUser | undefined;
  serverConfig: AmcatConfig;
  serverBranding: AmcatBranding;
}

function ServerSettings({ user, serverConfig, serverBranding }: ServerSettingsProps) {
  const { data: userDetails, isLoading: loadingUserDetails } = useCurrentUserDetails(user);
  const { data: users, isLoading: loadingUsers } = useUsers(user);
  const mutate = useMutateUser(user);

  if (loadingUserDetails || loadingUsers) return <Loading />;

  const ownRole = serverConfig?.authorization === "no_auth" ? "ADMIN" : userDetails?.role;
  async function changeRole(email: string | undefined, role: string, action: "create" | "delete" | "update") {
    mutate.mutateAsync({ email, role, action }).catch(console.error);
  }

  if (user == null || ownRole == null || users == null)
    return <div className="p-3">You don't have permission to see this</div>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex-auto">
        <UserRoleTable user={user} ownRole={ownRole} users={users} changeRole={changeRole} roles={roles} />
      </div>
      <UserTableInstructions serverConfig={serverConfig} />
    </div>
  );
}

function UserTableInstructions({ serverConfig }: { serverConfig: AmcatConfig }) {
  return (
    <InfoBox title="Information on server user management" storageKey="infobox:server-users">
      <div className="flex flex-col gap-5 text-sm">
        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Server roles vs project roles</h4>
          <p className="mb-2">
            AmCAT has two types of user roles: <b>server roles</b> and <b>project roles</b>.
          </p>
          <ul className="list-disc pl-5 flex flex-col gap-1">
            <li>
              <b>Server roles</b> determine which users can create projects and edit server settings. These should only
              be given to a few trusted users, who also take responsibility for maintaining the server.
            </li>
            <li>
              <b>Project roles</b> determine access to individual project data and settings. These are assigned by
              project ADMINs. You do not need a server role to be a project ADMIN.
            </li>
          </ul>
        </section>

        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Server roles</h4>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[4rem_1fr] gap-3">
              <b className="text-primary">WRITER</b>
              Can create and manage their own projects. Access to other projects is still restricted by project role.
              <b className="text-primary">ADMIN</b>
              Can manage all projects and users. Only give this to trusted users — they have access to all data on the server.
            </div>
          </div>
          <p className="mt-2">
            The WRITER role can also be given to any email address on a given domain, like <b>*@my-university.com</b>.
          </p>
        </section>

        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Project roles</h4>
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
            Projects can also set a guest role — see the project users page for details.
          </p>
        </section>

        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Authorization policy</h4>
          <p className="mb-2">
            This server has the authorization policy set to <b>{serverConfig.authorization}</b>. This can only be
            changed by editing the server configuration file.
          </p>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[12rem_1fr] gap-3">
              <b className="text-primary">NO AUTH</b>
              Authentication is disabled, and anyone can do anything. Only recommended for local use on your own device.
              <b className="text-primary">ALLOW GUESTS</b>
              Anyone can view and search public projects. Logged-in visitors can have additional permissions based on their user role.
              <b className="text-primary">ALLOW AUTHENTICATED GUESTS</b>
              Only authenticated users can view projects. Anyone can authenticate, but this adds a small barrier to entry, which can reduce spam and misuse.
            </div>
          </div>
        </section>
      </div>
    </InfoBox>
  );
}

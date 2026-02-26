import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/users")({
  component: Users,
});

import { useAmcatBranding } from "@/api/branding";
import { useAmcatConfig } from "@/api/config";
import { useCurrentUserDetails } from "@/api/userDetails";
import { useMutateUser, useUsers } from "@/api/users";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AmcatSessionUser, useAmcatSession } from "@/components/Contexts/AuthProvider";
import { Loading } from "@/components/ui/loading";
import UserRoleTable from "@/components/Users/UserRoleTable";

import { AmcatBranding, AmcatConfig } from "@/interfaces";
import { Info } from "lucide-react";

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
    <div className={`mx-auto grid max-w-[600px] grid-cols-1 gap-24 lg:max-w-full lg:grid-cols-2 lg:gap-12`}>
      <div className="flex-auto">
        <UserRoleTable user={user} ownRole={ownRole} users={users} changeRole={changeRole} roles={roles} />
      </div>
      <UserTableInstructions serverConfig={serverConfig} />
    </div>
  );
}

function UserTableInstructions({ serverConfig }: { serverConfig: AmcatConfig }) {
  return (
    <div className="prose-sm flex flex-col  px-3 dark:prose-invert">
      <div className="mb-3 flex items-center gap-3 text-primary">
        <Info className="inline h-6 w-6" />
        About user roles and authorization policy
      </div>
      <Tabs defaultValue="authorization policy">
        <TabsList className="mb-1">
          <TabsTrigger value="authorization policy">Authorization policy</TabsTrigger>
          <TabsTrigger value="user roles">User roles</TabsTrigger>
          <TabsTrigger value="examples">Examples</TabsTrigger>
        </TabsList>
        <TabsContent value="authorization policy">
          <p>
            This server has the authorization policy set to <b>{serverConfig.authorization}</b>. This can only be
            changed by editing the server configuration file (so not via this webclient or the API).
          </p>
          <div className="mb-2">There are four authorization policies:</div>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[8rem,1fr] gap-3">
              <b className="text-primary">NO AUTH</b>
              No authentication or authorization. Anyone can do anything. This is only recommended for local use on your
              own device.
              <b className="text-primary">ALLOW GUESTS</b>
              Anyone can view and search projects that have given access to "guests". Visitors that are logged in can
              have additional permissions based on their user role.
              <b className="text-primary">ALLOW AUTHENTICATED GUESTS</b>
              Like ALLOW GUESTS, but guests do need to authenticate by signing in. This adds a small barrier to entry,
              which can reduce spam and misuse.
              <b className="text-primary">AUTHORIZED USERS ONLY</b>
              Only users that have a role on the server can do anything. (See user management)
            </div>
          </div>
        </TabsContent>
        <TabsContent value="user roles">
          <p>There are three server access roles with incremental permissions:</p>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[4rem,1fr] gap-3">
              <b className="text-primary">READER</b>
              In AUTHORIZED USERS ONLY mode (see authorization policy), projects are only visible to users with the
              READER role or higher.
              <b className="text-primary">WRITER</b>
              Can create and manage their own projects.
              <b className="text-primary">ADMIN</b>
              Can manage all projects and users.
            </div>
          </div>
          <p>
            You can also assign a role to all email addresses that belong to a specific domain, using{" "}
            <b>*@domain.com</b>. This way you can for instance limit access to only members of your organization.
          </p>
        </TabsContent>
        <TabsContent value="examples">
          <h4>A restrictive set-up for use within an organization only</h4>
          <ul className="mt-0">
            <li>
              Set authorization policy to <b>authorized only</b>
            </li>
            <li>
              Give the USER role to <b>*@your-organization.com</b>.
            </li>
            <li>Give admin role to specific set of trusted users</li>
            <li>Admins determine who get to be WRITERs</li>
          </ul>
          <p>
            With this set-up, only members of your organization can access any data, and only trusted admins can change
            this. Writers can create and manage their own projects, but they cannot give access to users outside of the
            organization.
          </p>
          <h4>A public server that anyone in your organization can use to manage and share data</h4>
          <ul className="mt-0">
            <li>
              Set authorization policy to <b>allow guests</b>
            </li>
            <li>
              Give the WRITER role to <b>*@your-organization.com</b>
            </li>
          </ul>
          <p>
            With this set-up, anyone in your organization can create and manage their own projects. Visitors, even when
            not logged in, are considered "guests" and can search and view data in projects that have given access to
            "guests".
          </p>
        </TabsContent>
      </Tabs>
    </div>
  );
}

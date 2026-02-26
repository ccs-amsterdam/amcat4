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
      <Tabs defaultValue="amcat roles">
        <TabsList className="mb-1">
          <TabsTrigger value="amcat roles">AMCAT roles</TabsTrigger>
          <TabsTrigger value="server roles">Server roles</TabsTrigger>
          <TabsTrigger value="project roles">project roles</TabsTrigger>
          <TabsTrigger value="authorization policy">Authorization policy</TabsTrigger>
        </TabsList>

        <TabsContent value="amcat roles">
          <p>
            If you're here, you likely carry some responsibility over this AMCAT server, and you should know a bit about
            AMCAT user roles. Here we provide a brief summary.
          </p>
          <h3 className="font-bold text-primary">Server roles and project roles</h3>
          <p>
            AMCAT servers have two types of user roles: <b>server roles</b> and <b>project roles</b>.
            <ul className="list-disc pl-6">
              <li>
                <b>server roles</b> determine which users can create projects and edit server settings. These roles
                should only be given to a few trusted users. Server roles also come with a responsibility to maintain
                the server, and server users can get requests for allowing the creation of new projects.
              </li>
              <li>
                <b>project roles</b> determine which users can edit project settings and access project data. These
                roles are assigned by project ADMINs, that are responsible for the data in that project. Note that you
                do not need to have a server role to be a project ADMIN.
              </li>
            </ul>
          </p>
          <h3 className="font-bold text-primary">Roles are bound to email addresses</h3>
          <p>
            All roles are bound to email addresses. This can be specified at two levels:
            <ul className="list-disc pl-6">
              <li>
                <b>EXACT: </b>A role assigned to a specific user (user@university.com)
              </li>
              <li>
                <b>DOMAIN:</b> Anyone with an email address on the domain (*@my-university.com) gets the role
              </li>
            </ul>
            The domain level roles are convenient, but should be used with care. For this reason the ADMIN role is not
            allowed for this level.
          </p>
          <h3 className="font-bold text-primary">Projects have guest roles</h3>
          <p>
            Projects can also set a GUEST role. This means that the role applies to any email address, or even to anyone
            that visits the website (see <b>Authorization policy</b>). T
          </p>
          <p>
            The guest role is the best way to create public data. Project ADMINs have granular control over what content
            guest are able to see. For instance, should they only be able to find the project, or can they also search
            through the data? And if so, what parts of the documents are they allowed to see?{" "}
          </p>
        </TabsContent>
        <TabsContent value="server roles">
          <p>There are two server access roles:</p>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[4rem,1fr] gap-3">
              <b className="text-primary">WRITER</b>
              Users with the WRITER role can create and manage new projects. But their access to other projects is still
              restricted by their project role. So the only damage a WRITER can do is to clutter the server.
              <b className="text-primary">ADMIN</b>
              ADMINs can manage all projects and users. This role should only be given to trusted users, because they
              will have access to all data on the server, and can properly break things
            </div>
          </div>
          <p>
            The WRITER role can also be given to any email address on a given domain, like <b>*@my-university.com</b>.
          </p>
        </TabsContent>

        <TabsContent value="project roles">
          <p>
            Every project has it's own users table, where you can set the following roles with incremental permissions
          </p>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[5rem,1fr] gap-3">
              <b className="text-primary">OBSERVER</b>
              Can find the project and see the project metadata, but cannot search documents
              <b className="text-primary">META READER</b>
              Can also search documents, but only view document metadata. Project ADMINs can determine which fields are
              considered metadata.
              <b className="text-primary">READER</b>
              Can view all document data
              <b className="text-primary">WRITER</b>
              Can upload and edit documents
              <b className="text-primary">ADMIN</b>
              Can manage users, edit project settings and break things
            </div>
          </div>
          <p>
            Project roles (except for ADMIN) can also be given to any email address on a given domain, like{" "}
            <b>*@my-university.com</b>.
          </p>
        </TabsContent>
        <TabsContent value="authorization policy">
          <p>
            This server has the authorization policy set to <b>{serverConfig.authorization}</b>. This can only be
            changed by editing the server configuration file.
          </p>
          <div className="mb-2">There are three authorization policies:</div>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[8rem,1fr] gap-3">
              <b className="text-primary">NO AUTH</b>
              Authentication is desabled, and anyone can do anything. This is only recommended for local use on your own
              device.
              <b className="text-primary">ALLOW GUESTS</b>
              Anyone can view and search public projects. Visitors that are logged in can have additional permissions
              based on their user role.
              <b className="text-primary">ALLOW AUTHENTICATED GUESTS</b>
              Only authenticated users can view projects. Anyone can authenticate, but this adds a small barrier to
              entry, which can reduce spam and misuse.
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

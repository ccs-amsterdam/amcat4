import { createFileRoute } from "@tanstack/react-router";

import { useMyGlobalRole } from "@/api/userDetails";
import { HelpCircle } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

import { RequestRoleChange } from "@/components/Access/RequestRoleChange";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

const roles = ["NONE", "WRITER", "ADMIN"];

export const Route = createFileRoute("/access")({
  component: ServerRole,
});

function ServerRole() {
  const { user } = useAmcatSession();

  const user_role = useMyGlobalRole(user) || "NONE";

  function myRole() {
    if (user_role === "NONE") return <span>you do not have a role on this server</span>;
    return (
      <span>
        You have the <b>{user_role}</b> role on this server.
      </span>
    );
  }

  function requestRoleChange() {
    if (!user) return null;
    if (user_role === "ADMIN") return null;
    return <RequestRoleChange user={user} roles={roles} currentRole={user_role} />;
  }

  // TODO: Add contact info on server client_data, then uncomment this
  //
  // function pointsOfContact() {
  //   if (project?.contact)
  //     return (
  //       <div className=" mt-6  max-w-xl items-center gap-3 rounded-md">
  //         <div className="p-3">
  //           <div className="text-lg font-bold">Contact information</div>
  //           <div className="text-sm">
  //             For other questions or comments about the accessibility of data in this project, you can reach out to:
  //           </div>
  //         </div>
  //         <div className="items-center rounded-md  p-3 text-sm ">
  //           <ContactInfo contact={project?.contact} />
  //         </div>
  //       </div>
  //     );
  // }

  return (
    <div className="mt-12 flex flex-col gap-6 p-6">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <div className=" flex items-center gap-3 py-3">
          {myRole()}
          <RoleInfoDialog />
        </div>
        {requestRoleChange()}
      </div>
    </div>
  );
}

function RoleInfoDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <HelpCircle className="cursor-pointer text-primary" />
      </DialogTrigger>
      <DialogContent className="w-[600px] max-w-[95vw]">
        <DialogTitle className="">Server access roles</DialogTitle>
        <DialogDescription className="">
          AmCAT has two types of roles: Server level access and Project level access. Any user can be given a role on a
          project, but only users with a server level role can create new projects or manage users.
        </DialogDescription>
        <RoleInfo />
      </DialogContent>
    </Dialog>
  );
}

function RoleInfo() {
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="grid grid-cols-[7rem,1fr] gap-1">
        <b className="text-primary">NO ROLE</b>
        Can be given a role on a project, and can request a new project.
        <b className="text-primary">WRITER</b>
        Can create new projects, and approve new project requests.
        <b className="text-primary">ADMIN</b>
        Can manage all projects and users.
      </div>
    </div>
  );
}

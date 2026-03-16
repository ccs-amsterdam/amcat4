import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ChevronDown } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Textarea } from "../ui/textarea";
import { AmcatProjectId } from "@/interfaces";
import CodeExample from "@/components/CodeExample/CodeExample";
import UsersHelpDialog from "./UsersHelpDialog";

interface Props {
  ownRole: string;
  roles: string[];
  changeRole: (email: string, role: string, action: "create" | "delete" | "update") => void | Promise<void>;
  projectId?: AmcatProjectId;
  children?: React.ReactNode;
}

export default function CreateUser({ children, ownRole, roles, changeRole, projectId }: Props) {
  const [open, setOpen] = useState(false);
  const doCreateUser = async (email: string, role: string) => {
    changeRole(email, role, "create");
    setOpen(false);
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="w-96 max-w-[100vw]">
        <DialogHeader>
          <DialogTitle>Add Users</DialogTitle>
        </DialogHeader>
        <CreateUserForm ownRole={ownRole} roles={roles} projectId={projectId} createUser={doCreateUser} />
      </DialogContent>
    </Dialog>
  );
}

interface CreateUserProps {
  ownRole: string;
  roles: string[];
  projectId?: AmcatProjectId;
  createUser: (email: string, role: string) => void;
  children?: React.ReactNode;
}

function CreateUserForm({ ownRole, roles, projectId, createUser }: CreateUserProps) {
  const [emails, setEmails] = useState("");
  const [role, setRole] = useState(() => roles[0]);

  const { user } = useAmcatSession();

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!emails || !role) return;

    const emailList = emails
      .split("\n")
      .map((email) => email.trim())
      .filter((email) => email);

    const invalidEmails = emailList.filter(
      (email) => !z.string().email().safeParse(email.replace(/^\*@/, "__EVERYONE__@")).success,
    );
    if (invalidEmails.length > 0) {
      toast(`Invalid emails: ${invalidEmails.join(", ")}`);
      return;
    }

    for (const email of emailList) {
      createUser(email, role);
    }
  }

  return (
    <form onSubmit={onSubmit} className="prose flex max-w-none flex-col gap-3 dark:prose-invert">
      <Textarea
        rows={6}
        required
        value={emails}
        onChange={(e) => setEmails(e.target.value)}
        placeholder="user1@userland.com&#10;user2@userland.com&#10;*@my-university.com"
      />
      <DropdownMenu>
        <DropdownMenuTrigger className="flex h-9 w-full items-center justify-between gap-3 rounded border border-primary px-3 text-primary outline-none">
          {role}
          <ChevronDown className="h-5 w-5" />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuRadioGroup value={role} onValueChange={setRole}>
            {roles.map((role) => {
              if (ownRole !== "ADMIN" && ownRole !== "WRITER") return null;
              if (ownRole === "WRITER" && role === "ADMIN") return null;
              if (role === "NONE") return null;
              return (
                <DropdownMenuRadioItem key={role} value={role}>
                  {role}
                </DropdownMenuRadioItem>
              );
            })}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <div className="flex items-center justify-between gap-2">
        <UsersHelpDialog roles={roles} />
        <div className="flex items-center gap-2">
          <CodeExample action="add_user" projectId={projectId} emails={emails.split("\n").map((e) => e.trim()).filter(Boolean)} role={role} />
          <Button disabled={!user}>Create</Button>
        </div>
      </div>
    </form>
  );
}

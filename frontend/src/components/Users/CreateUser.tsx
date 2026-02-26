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

interface Props {
  ownRole: string;
  roles: string[];
  changeRole: (email: string, role: string, action: "create" | "delete" | "update") => void | Promise<void>;
  children?: React.ReactNode;
}

export default function CreateUser({ children, ownRole, roles, changeRole }: Props) {
  const [open, setOpen] = useState(false);
  const doCreateUser = async (email: string, role: string) => {
    changeRole(email, role, "create");
    setOpen(false);
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Users</DialogTitle>
        </DialogHeader>
        <CreateUserForm ownRole={ownRole} roles={roles} createUser={doCreateUser} />
      </DialogContent>
    </Dialog>
  );
}

interface CreateUserProps {
  ownRole: string;
  roles: string[];
  createUser: (email: string, role: string) => void;
  children?: React.ReactNode;
}

function CreateUserForm({ ownRole, roles, createUser }: CreateUserProps) {
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
        placeholder="user1@userland.com&#10;user2@userland.com"
      />
      <div className="grid grid-cols-[2fr,1fr] gap-3">
        <DropdownMenu>
          <DropdownMenuTrigger className="flex h-full items-center justify-between gap-3 rounded border border-primary px-3 text-primary outline-none">
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
        <Button disabled={!user}>Create</Button>
      </div>
    </form>
  );
}

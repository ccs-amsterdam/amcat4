import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { HelpCircle } from "lucide-react";

const roleDescriptions: Record<string, string> = {
  OBSERVER: "Can find the project and see project metadata, but cannot search documents.",
  METAREADER: "Can search documents, but only view document metadata. Project ADMINs control which fields count as metadata.",
  READER: "Can view all document data.",
  WRITER: "Can upload and edit documents.",
  ADMIN: "Can manage users, edit project settings and break things.",
};

export default function UsersHelpDialog({ roles }: { roles: string[] }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <HelpCircle className="cursor-pointer text-primary" />
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Role reference</DialogTitle>
        </DialogHeader>
        <div className="divide-y rounded border text-sm">
          {roles.filter((r) => r !== "NONE").map((role) => (
            <div key={role} className="flex items-start gap-3 px-3 py-2">
              <span className="w-24 shrink-0 font-mono font-medium text-primary">{role}</span>
              <span className="text-muted-foreground">{roleDescriptions[role] ?? ""}</span>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

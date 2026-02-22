import { DataTable } from "@/components/ui/datatable";
import { AmcatUserDetails, AmcatUserRole } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { ColumnDef } from "@tanstack/react-table";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuRadioItem,
  DropdownMenuRadioGroup,
} from "@/components/ui/dropdown-menu";
import { amcatUserRoleSchema } from "@/schemas";
import { ArrowUpDown, ChevronDown, Search, UserMinus, UserPlus } from "lucide-react";
import { ErrorMsg } from "@/components/ui/error-message";
import { roleHigherThan } from "@/api/util";
import { useEffect, useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
} from "@/components/ui/alert-dialog";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import CreateUser from "./CreateUser";

interface Props {
  user: AmcatSessionUser;
  ownRole: AmcatUserRole;
  users: AmcatUserDetails[];
  roles: string[];
  changeRole: (email: string | undefined, role: string, action: "create" | "delete" | "update") => void;
}

// This components works for both Server and Index users, depending
// on the props passed in.

export default function UserRoleTable({ user, ownRole, users, roles, changeRole }: Props) {
  const [changeOwnRole, setChangeOwnRole] = useState<string | undefined>(undefined);
  const [tableColumns] = useState<ColumnDef<Row>[]>(() => createTableColumns(roles));
  const [globalFilter, setGlobalFilter] = useState("");
  const [debouncedGlobalFilter, setDebouncedGlobalFilter] = useState(globalFilter);

  useEffect(() => {
    const timeout = setTimeout(() => {
      setGlobalFilter(debouncedGlobalFilter);
    }, 250);
    return () => clearTimeout(timeout);
  }, [debouncedGlobalFilter]);

  if (!["ADMIN", "WRITER"].includes(ownRole))
    return <ErrorMsg type="Not Allowed">Need to have the WRITER or ADMIN role to edit index users</ErrorMsg>;

  function onChangeRole(email: string, currentRole: AmcatUserRole, newRole: string) {
    const role = amcatUserRoleSchema.parse(newRole);
    if (currentRole === role) return;
    if (email === user?.email && roleHigherThan(currentRole, role)) {
      // if the user is changing their own role to a lower role, we need to ask for confirmation
      setChangeOwnRole(newRole);
      return;
    }
    changeRole(email, newRole, newRole === "NONE" ? "delete" : "update");
  }
  function confirmChangeOwnRole() {
    if (!user || !changeOwnRole) return;
    changeRole(user.email, changeOwnRole, changeOwnRole === "NONE" ? "delete" : "update");
  }

  const data: Row[] =
    users?.map((user) => {
      const row: Row = { ...user, canCreateAdmin: ownRole === "ADMIN" };
      const canEditUser = ownRole === "ADMIN" || (ownRole === "WRITER" && user.role !== "ADMIN");
      if (canEditUser) row.onChange = (newRole: string) => onChangeRole(user.email, user.role, newRole);
      return row;
    }) || [];

  return (
    <div className=" w-full max-w-7xl grid-cols-1">
      <div className="flex items-center justify-between pb-4">
        <div className="prose-xl flex gap-1 md:gap-3">
          <h3 className="mb-0">User Roles</h3>
          <CreateUser ownRole={ownRole} roles={roles} changeRole={changeRole}>
            <Button variant="ghost" className="flex gap-2 p-4">
              <UserPlus />
              <span className="hidden sm:inline">Add user</span>
            </Button>
          </CreateUser>
        </div>
        <div className="relative ml-auto flex items-center">
          <Input
            className="max-w-1/2 w-40 pl-8"
            value={debouncedGlobalFilter}
            onChange={(e) => setDebouncedGlobalFilter(e.target.value)}
          />
          <Search className="absolute left-2  h-5 w-5" />
        </div>
      </div>
      <div>
        <DataTable columns={tableColumns} data={data} globalFilter={globalFilter} pageSize={50} />
        <AlertDialog open={changeOwnRole !== undefined} onOpenChange={() => setChangeOwnRole(undefined)}>
          <AlertDialogContent>
            <AlertDialogHeader>Are you sure you want to limit your own role?</AlertDialogHeader>
            <AlertDialogDescription>
              You are about to change your own role from {ownRole} to {changeOwnRole}. You will not be able to change
              this back yourself.
            </AlertDialogDescription>
            <AlertDialogFooter>
              <AlertDialogCancel>Oh god no!</AlertDialogCancel>
              <AlertDialogAction onClick={confirmChangeOwnRole}>Do it!!</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}

interface Row {
  email: string;
  role: string;
  canCreateAdmin: boolean;
  onChange?: (newRole: string) => void;
}

function createTableColumns(roles: string[]): ColumnDef<Row>[] {
  return [
    {
      accessorKey: "email",
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            className="active:transparent pl-0 hover:bg-transparent"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          >
            Email
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      size: 400,
    },
    {
      accessorKey: "role",
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            className="active:transparent pl-0 hover:bg-transparent"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          >
            Role
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      enableResizing: false,
      size: 100,
      cell: ({ row }) => {
        const { role, canCreateAdmin, onChange } = row.original;
        if (!onChange) return role;
        return (
          <DropdownMenu>
            <DropdownMenuTrigger className="flex h-full items-center gap-3 border-primary text-primary outline-none">
              {role === "NONE" ? "DELETE" : role}
              <ChevronDown className="h-4 w-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuRadioGroup value={row.original.role} onValueChange={onChange}>
                {roles.map((role) => {
                  if (!canCreateAdmin && role === "ADMIN") return null;
                  return (
                    <DropdownMenuRadioItem key={role} value={role}>
                      {role === "NONE" ? "DELETE" : role}
                    </DropdownMenuRadioItem>
                  );
                })}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
    {
      id: "actions",
      meta: { align: "right", textAlign: "right" },
      cell: ({ row }) => {
        const { onChange } = row.original;
        if (!onChange) return null;
        return <DeleteUserAction onChange={onChange} />;
      },
    },
  ];
}

function DeleteUserAction({ onChange }: { onChange: (newRole: string) => void }) {
  const [input, setInput] = useState("");

  return (
    <div className="flex w-full justify-end ">
      <Popover onOpenChange={() => setInput("")}>
        <PopoverTrigger asChild className="">
          <UserMinus className="h-6 w-6 cursor-pointer  " />
        </PopoverTrigger>
        <PopoverContent>
          <div className="flex flex-col gap-2">
            <span>Are you sure you want to delete this user? Type "yes"</span>
            <Input value={input} placeholder='type "yes" to confirm' onChange={(e) => setInput(e.target.value)} />
            <div className="grid grid-cols-2 gap-1">
              <PopoverClose asChild>
                <Button disabled={input.toLowerCase() !== "yes"} variant="destructive" onClick={() => onChange("NONE")}>
                  Delete
                </Button>
              </PopoverClose>
              <PopoverClose asChild>
                <Button variant="outline">Cancel</Button>
              </PopoverClose>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

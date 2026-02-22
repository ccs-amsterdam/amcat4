import { useDeleteIndex, useHasIndexRole, useMutateIndex } from "@/api";
import { Button } from "@/components/ui/button";
import { AmcatIndex } from "@/interfaces";
import { ArchiveRestore, ArchiveX, CornerLeftUp, FolderPlus, MoreVertical, Trash2 } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import React, { useState } from "react";
import { ActivateConfirm } from "../ui/confirm";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Input } from "../ui/input";

export function IndexDropdownMenu({
  index,
  folders,
  toFolder,
  activateConfirm,
}: {
  index: AmcatIndex;
  folders: string[];
  toFolder: (folder: string) => void;
  activateConfirm: ActivateConfirm;
}) {
  const [isNewFolderDialogOpen, setIsNewFolderDialogOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState(index.folder || "");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  const { user } = useAmcatSession();
  const { mutateAsync } = useMutateIndex(user);
  const { mutateAsync: deleteAsync } = useDeleteIndex(user);

  const isAdmin = index.user_role === "ADMIN";

  function handleDelete() {
    deleteAsync(index.id);
  }

  function handleArchive(e: React.MouseEvent) {
    e.preventDefault();
    mutateAsync({ id: index.id, archive: !index.archived }).then(() => setIsDropdownOpen(false));
  }

  function doMoveToFolder(folder: string) {
    const f = folder.replace(/\/+/g, "/").replace(/^\/|\/$/g, "");
    mutateAsync({ id: index.id, folder: f }).then(() => {
      setIsDropdownOpen(false);
      setIsNewFolderDialogOpen(false);
      toFolder(f || "");
    });
  }

  function handleRelativeMove(e: Event, folder: string) {
    e.preventDefault();

    let newFolder = "";
    if (folder === "..") {
      newFolder = index.folder ? index.folder.split("/").slice(0, -1).join("/") : "";
    } else {
      newFolder = index.folder ? `${index.folder}/${folder}` : folder;
    }
    doMoveToFolder(newFolder);
  }

  function handleAboluteMove(e: React.MouseEvent) {
    e.preventDefault();
    doMoveToFolder(newFolderName);
  }

  if (!isAdmin) return null;

  return (
    <>
      <DropdownMenu modal={false} open={isDropdownOpen} onOpenChange={setIsDropdownOpen}>
        <DropdownMenuTrigger
          asChild
          onClick={(e) => {
            e.preventDefault();
            // setIsDropdownOpen(!isDropdownOpen);
          }}
        >
          <Button variant="ghost" className="h-8 w-8 p-0">
            <span className="sr-only">Open menu</span>
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenuItem onClick={handleArchive} className="flex items-center gap-3">
            {index.archived ? <ArchiveRestore className="h-4 w-4" /> : <ArchiveX className="h-4 w-4" />}
            <span>{index.archived ? "Re-activate" : "Archive"}</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            className="flex items-center gap-3"
            onClick={() =>
              activateConfirm(handleDelete, {
                description: `You are about to delete index ${index.name}. This cannot be undone!`,
                challenge: index.id,
                confirmText: `Delete index ${index.name}`,
              })
            }
          >
            <Trash2 className="h-4 w-4" />
            <span>Delete</span>
          </DropdownMenuItem>
          <Dialog
            open={isNewFolderDialogOpen}
            onOpenChange={(open) => {
              if (!open) setIsDropdownOpen(false);
              setIsNewFolderDialogOpen(false);
            }}
          >
            <DialogTrigger asChild>
              <DropdownMenuItem
                className="flex items-center gap-3"
                onSelect={(e) => {
                  e.preventDefault();
                  setIsNewFolderDialogOpen(true);
                }}
              >
                <FolderPlus className="h-4 w-4" />
                <span>{index.folder ? "change folder" : "move to folder"}</span>
              </DropdownMenuItem>
            </DialogTrigger>
            <DialogContent onClick={(e) => e.stopPropagation()}>
              <DialogHeader>
                <DialogTitle>Move to folder</DialogTitle>
                <DialogDescription>This will create a new folder and move the index to that folder</DialogDescription>
              </DialogHeader>
              <Input
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                placeholder="Enter folder name"
              />
              <Button onClick={handleAboluteMove}>Create and Move</Button>
            </DialogContent>
          </Dialog>
          <DropdownMenuGroup className={folders?.length ? "" : "hidden"}>
            <DropdownMenuSeparator />

            <DropdownMenuLabel className="text-foreground">
              <span>Move to folder</span>
            </DropdownMenuLabel>
            {index.folder && (
              <DropdownMenuItem key={".."} onSelect={(e) => handleRelativeMove(e, "..")}>
                <CornerLeftUp className="ml-4 h-3 w-3" />
                <span className="ml-1">{index.folder.split("/")[index.folder.split("/").length - 2] || "Root"}</span>
              </DropdownMenuItem>
            )}
            {folders.map((folder) => (
              <DropdownMenuItem key={folder} onSelect={(e) => handleRelativeMove(e, folder)}>
                <span className="ml-4">{folder}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}

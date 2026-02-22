import { useEffect, useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "./alert-dialog";
import { Input } from "./input";

export type ActivateConfirm = (callback: () => void, options?: ConfirmOptions) => void;

export function useConfirm() {
  const [confirmCallback, setConfirmCallback] = useState<() => void>();
  const [confirmOptions, setConfirmOptions] = useState<ConfirmOptions>({});

  const activate: ActivateConfirm = (callback: () => void, options?: ConfirmOptions) => {
    if (options != null) setConfirmOptions(options);
    setConfirmCallback(() => callback);
  };

  return {
    activate,
    confirmDialog: (
      <Confirm
        onConfirm={confirmCallback}
        onClose={() => {
          setConfirmCallback(undefined);
        }}
        {...confirmOptions}
      />
    ),
  };
}

interface ConfirmOptions {
  title?: string;
  description?: string;
  challenge?: string;
  danger?: boolean;
  confirmText?: string;
}

interface ConfirmProps extends ConfirmOptions {
  onClose: () => void;
  onConfirm: (() => void) | undefined;
}
export default function Confirm({
  onClose,
  onConfirm,
  title,
  description,
  challenge,
  danger,
  confirmText,
}: ConfirmProps) {
  const [challengeValue, setChallengeValue] = useState("");
  // Erase challenge on open
  useEffect(() => {
    setChallengeValue("");
  }, [onClose]);

  const handleConfirm = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onConfirm != null) {
      onConfirm();
    }
    onClose();
  };
  if (danger == null) danger = !!challenge;
  return (
    <AlertDialog open={!!onConfirm} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogTitle>{title ?? "Are you sure?"}</AlertDialogTitle>
        <AlertDialogDescription>{description ?? "Please confirm the action"}</AlertDialogDescription>
        {!challenge ? null : (
          <div className="mt-4 space-y-2">
            <div>
              Please type <code className="rounded px-1 py-0.5 text-sm text-red-600">{challenge}</code> to confirm:
            </div>
            <Input value={challengeValue} onChange={(e) => setChallengeValue(e.target.value)} />
          </div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={!!challenge && challenge != challengeValue}
            onClick={handleConfirm}
            className={!danger ? "" : "bg-destructive text-destructive-foreground hover:bg-destructive/80"}
          >
            {confirmText ?? "Continue"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

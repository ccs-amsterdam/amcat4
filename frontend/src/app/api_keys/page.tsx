"use client";

import { useApiKeys, useMutateApiKeys } from "@/api/api_keys";
import { CreateApiKey } from "@/components/Server/CreateApiKey";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ui/confirm";
import { AmcatApiKey } from "@/interfaces";
import { Check, Clipboard, Cog, Recycle, Trash2 } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useState } from "react";
import { toast } from "sonner";

type CreateKey = AmcatApiKey | "new" | null;

export default function Page() {
  const { user } = useAmcatSession();
  const { data: apiKeys } = useApiKeys(user);
  const [createKey, setCreateKey] = useState<CreateKey>(null);
  const [showKey, setShowKey] = useState<string>("");

  if (showKey) return <ShowKey showKey={showKey} setShowKey={setShowKey} setCreateKey={setCreateKey} />;

  if (createKey) {
    return <CreateApiKeyForm createKey={createKey} setCreateKey={setCreateKey} setShowKey={setShowKey} />;
  }

  return (
    <div className="mx-auto mt-12 flex w-full max-w-3xl flex-col px-6 py-6">
      <Button className="ml-auto" onClick={() => setCreateKey("new")}>
        Create API Key
      </Button>
      <div className="flex flex-col">
        {apiKeys?.map((key) => (
          <div key={key.id} className="mt-4 rounded bg-primary/10 p-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="mt-0 text-lg font-medium">
                  {key.name || <span className=" text-foreground/50">unnamed</span>}
                </h3>
                <div className="">
                  {key.expires_at && <p className="text-sm">Expires at: {new Date(key.expires_at).toLocaleString()}</p>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <RegenerateButton apikey={key} setShowKey={setShowKey} />
                <DeleteButton apikey={key} />
                <Button variant="ghost" size="icon" onClick={() => setCreateKey(key)}>
                  <Cog />
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ShowKey({
  showKey,
  setShowKey,
  setCreateKey,
}: {
  showKey: string;
  setShowKey: (key: string) => void;
  setCreateKey: (key: CreateKey) => void;
}) {
  const [copied, setCopied] = useState(false);
  function copyToClipboard() {
    navigator.clipboard.writeText(showKey);
    toast.success("API key copied to clipboard");
    setCopied(true);
  }

  return (
    <div className="mx-auto mt-12 flex w-full max-w-3xl flex-col px-6 py-6">
      <h2 className="mb-4 text-2xl font-bold">API Key Created</h2>
      <p className="mb-4">Please copy and store your API key securely. You won't be able to see it again!</p>
      <div className="mb-4 flex items-center justify-between rounded bg-secondary/10 p-4 font-mono text-sm">
        {showKey}
        <Button variant="ghost" size="icon" onClick={copyToClipboard} title="Copy to clipboard">
          {copied ? <Check /> : <Clipboard />}
        </Button>
      </div>
      <Button
        onClick={() => {
          setShowKey("");
          setCreateKey(null);
        }}
      >
        Close
      </Button>
    </div>
  );
}

function DeleteButton({ apikey }: { apikey: AmcatApiKey }) {
  const { activate, confirmDialog } = useConfirm();
  const { user } = useAmcatSession();
  const { mutateAsync: mutateKey } = useMutateApiKeys(user);

  function onClick() {
    const handleDelete = () => mutateKey({ update: apikey, action: "delete" });
    activate(handleDelete, {
      description: `Are you sure you want to delete this API key? This action cannot be undone.`,
      confirmText: "Delete",
    });
  }

  return (
    <>
      {confirmDialog}
      <Button variant="ghost" size="icon" onClick={onClick}>
        <Trash2 />
      </Button>
    </>
  );
}

function RegenerateButton({ apikey, setShowKey }: { apikey: AmcatApiKey; setShowKey: (key: string) => void }) {
  const { activate, confirmDialog } = useConfirm();
  const { user } = useAmcatSession();
  const { mutateAsync: mutateKey } = useMutateApiKeys(user);

  function onClick() {
    const handleRegenerate = () =>
      mutateKey({
        update: apikey,
        action: "update",
        regenerate: true,
      }).then((apikey) => setShowKey(apikey || ""));
    activate(handleRegenerate, {
      description: `Are you sure you want to regenerate this API key? The old key will no longer work.`,
      confirmText: "Regenerate",
    });
  }

  return (
    <>
      {confirmDialog}
      <Button variant="ghost" size="icon" onClick={onClick}>
        <Recycle />
      </Button>
    </>
  );
}

function CreateApiKeyForm({
  createKey,
  setCreateKey,
  setShowKey,
}: {
  createKey: CreateKey;
  setCreateKey: (key: CreateKey) => void;
  setShowKey: (key: string) => void;
}) {
  if (createKey === null) return null;

  return (
    <div className="mx-auto mt-12 w-full max-w-2xl px-6 py-6">
      <CreateApiKey current={createKey} onClose={() => setCreateKey(null)} setShowKey={setShowKey} />
    </div>
  );
}

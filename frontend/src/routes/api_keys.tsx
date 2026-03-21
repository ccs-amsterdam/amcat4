import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api_keys")({
  component: ApiKeys,
});

import { useApiKeys, useMutateApiKeys } from "@/api/api_keys";
import { CreateApiKey } from "@/components/Server/CreateApiKey";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ui/confirm";
import { InfoBox } from "@/components/ui/info-box";
import { AmcatApiKey } from "@/interfaces";
import { Check, Clipboard, Cog, ExternalLink, LogInIcon, Recycle, Trash2 } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useState } from "react";
import { toast } from "sonner";
import { ErrorMsg } from "@/components/ui/error-message";

type CreateKey = AmcatApiKey | "new" | null;

export default function ApiKeys() {
  const { user } = useAmcatSession();
  const { data: apiKeys } = useApiKeys(user);
  const [createKey, setCreateKey] = useState<CreateKey>(null);
  const [showKey, setShowKey] = useState<string>("");

  if (showKey) return <ShowKey showKey={showKey} setShowKey={setShowKey} setCreateKey={setCreateKey} />;

  if (createKey) {
    return <CreateApiKeyForm createKey={createKey} setCreateKey={setCreateKey} setShowKey={setShowKey} />;
  }

  if (!user.authenticated) return <AuthRequired />;

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
      <InfoBox title="Information on API keys" storageKey="infobox:api-keys" className="mt-6">
        <div className="flex flex-col gap-2 text-sm">
          <p>
            An <strong>API key</strong> lets you access AmCAT programmatically — from a script or analysis pipeline —
            without having to log in interactively. Once created, pass the key when connecting to AmCAT from Python or R.
          </p>
          <p>
            Most screens in the interface have a <strong>Show code</strong> button that generates ready-to-use Python and R
            code for the current query or dataset. This is a good starting point for your own scripts.
          </p>
          <div className="flex flex-wrap gap-4">
            <a
              href="https://github.com/ccs-amsterdam/amcat4py"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              amcat4py (Python) <ExternalLink className="h-3 w-3" />
            </a>
            <a
              href="https://github.com/ccs-amsterdam/amcat4r"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              amcat4r (R) <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>
      </InfoBox>
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
      <p className="mb-4">Please copy and store your API key securely. You wont be able to see it again!</p>
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

function AuthRequired() {
  const { signIn } = useAmcatSession();

  return (
    <ErrorMsg type="Sign-in required">
      <p className="w-[500px] max-w-[95vw] text-center">Only authenticated users can create API keys</p>
      <Button className="mx-auto mt-6 flex items-center gap-2 pr-6" onClick={() => signIn()}>
        <LogInIcon className="mr-2 h-4 w-4" />
        Sign-in
      </Button>
    </ErrorMsg>
  );
}

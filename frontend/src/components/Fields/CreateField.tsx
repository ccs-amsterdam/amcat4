import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { AmcatField, AmcatFieldType, UpdateAmcatField } from "@/interfaces";
import { ChevronDown, HelpCircle, Key } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { DynamicIcon } from "../ui/dynamic-icon";
import { Input } from "../ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

interface Props {
  fields: AmcatField[];
  onCreate: (field: UpdateAmcatField) => void;
  children?: React.ReactNode;
}

export default function CreateField({ children, fields, onCreate }: Props) {
  const [open, setOpen] = useState(false);
  const doCreateField = async (field: UpdateAmcatField) => {
    onCreate(field);
    setOpen(false);
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Field</DialogTitle>
        </DialogHeader>
        <CreateFieldForm fields={fields} createField={doCreateField} />
      </DialogContent>
    </Dialog>
  );
}
interface CreateFieldProps {
  fields: AmcatField[];
  createField: (field: UpdateAmcatField) => void;
  children?: React.ReactNode;
}

function CreateFieldForm({ fields, createField }: CreateFieldProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [identifier, setIdentifier] = useState(false);
  const [type, setType] = useState<AmcatFieldType | null>(null);

  const disabled = !name || error !== "" || !type;

  async function onSubmit() {
    if (disabled) return;
    createField({ name, type, identifier });
  }

  return (
    <div className="prose flex max-w-none flex-col gap-4 overflow-auto p-1 dark:prose-invert">
      <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-[1fr,10rem]">
        <div>
          <CreateFieldNameInput name={name} setName={setName} setError={setError} fields={fields} />
        </div>
        <CreateFieldSelectType type={type} setType={setType} />
      </div>
      <div
        className=" flex w-max select-none items-center gap-3"
        onClick={() => {
          setIdentifier(!identifier);
        }}
      >
        <Key className="h-6 w-6" />
        <label className="">Use as identifier</label>
        <Checkbox className="ml-[2px] h-5 w-5" checked={identifier}>
          Field exists
        </Checkbox>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <CreateFieldInfoDialog />
        <span className="text-destructive">{error}</span>
        <Button className="" onClick={onSubmit} disabled={disabled}>
          Create
        </Button>
      </div>
    </div>
  );
}

const types = new Map<AmcatFieldType, string>([
  ["keyword", "A keyword field is useful for shorter labels or categories that should not be analysed"],
  ["text", "Text fields are used for longer texts; They are analysed so individual words can be searched"],
  ["date", "Field for date or date/time values"],
  ["boolean", "For boolean (true or false) values"],
  ["number", "For numeric values"],
  ["integer", "For integer values, i.e. numbers without decimals"],
  ["image", "Links to image files. (You can upload images to AmCAT on the multimedia page)"],
  ["video", "Links to video files. (You can upload videos to AmCAT on the multimedia page)"],
  ["audio", "Links to audio files. (You can upload audio to AmCAT on the multimedia page)"],
  ["object", "General objects that will not be parsed"],
  ["vector", "Dense vectors, i.e. document embeddings"],
  ["geo", "Geolocations, i.e. longitude and lattitude"],
  ["tag", "Tag fields can contain multiple tags for each document"],
]);

export function CreateFieldNameInput({
  name,
  setName,
  setError,
  fields,
}: {
  name: string | undefined;
  setName: (name: string) => void;
  setError: (error: string) => void;
  fields: AmcatField[];
}) {
  const validateFieldName = (value: string | undefined) => {
    if (!value) return ["", ""];
    // see https://github.com/elastic/elasticsearch/issues/9059 (why is this not properly documented?)
    // Field names should not start with underscore, and should not contain dots or backslashes
    // (and should probably not contain spaces?)
    let error = "";
    value = value.replace(/ /g, "_");
    value = value.replace(/[ \\.\\]/, "");
    value = value.replace(/^_+/, "");
    if (fields.find((f) => f.name === value)) error = `Field name already exists`;
    return [value, error];
  };

  const doSetField = (e: React.FormEvent<HTMLInputElement>) => {
    const [value, error] = validateFieldName((e.target as any).value);
    setError(error);
    setName(value);
  };

  useEffect(() => {
    const [value, error] = validateFieldName(name);
    setError(error);
    setName(value);
  }, [fields, name]);

  return <Input name="field_name" required value={name} onChange={doSetField} placeholder="Field_name" />;
}

export function CreateFieldSelectType({
  type,
  setType,
}: {
  type: AmcatFieldType | null;
  setType: (type: AmcatFieldType) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex h-full items-center justify-between gap-3 rounded border border-primary px-3 text-primary outline-none">
        {type ? (
          <>
            <DynamicIcon type={type} /> {type}
          </>
        ) : (
          "Select type"
        )}
        <ChevronDown className="h-5 w-5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="h-64 overflow-auto">
        <DropdownMenuRadioGroup value={type ?? undefined} onValueChange={(value) => setType(value as AmcatFieldType)}>
          {Array.from(types.entries()).map(([x, help]) => {
            return (
              <Tooltip key={x}>
                <TooltipTrigger asChild>
                  <DropdownMenuRadioItem value={x}>
                    <DynamicIcon type={x} /> &nbsp;{x}
                  </DropdownMenuRadioItem>
                </TooltipTrigger>{" "}
                <TooltipContent side="right" className="w-44">
                  {help}
                </TooltipContent>
              </Tooltip>
            );
          })}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function CreateFieldInfoDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <HelpCircle className="cursor-pointer text-primary" />
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>Creating a new project field</DialogHeader>
        <p className="text-sm">
          When creating a new project field, you need to pick a name and type. The type indicates how the data will be
          stored in Elasticsearch. Make sure to pick a suitable type, because you won't be able to change this after the
          field has been created.
        </p>
        <p className="text-sm">
          If a field is marked as an <i>identifier</i>, it will be used to prevent duplicate documents (like a primary
          key in SQL). Use a unique identifier (e.g., URL) if available. Use multiple identifiers for unique
          combinations (e.g., author & timestamp).{" "}
          <span className="text-primary">
            You won't be able to change this afterwards, and identifiers are also immutable (i.e. cannot be updated).
          </span>
        </p>
      </DialogContent>
    </Dialog>
  );
}

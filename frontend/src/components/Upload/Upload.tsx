import { useFields } from "@/api/fields";
import {
  AmcatElasticFieldType,
  AmcatField,
  AmcatFieldType,
  AmcatProjectId,
  UpdateAmcatField,
  UploadOperation,
} from "@/interfaces";
import { AlertCircleIcon, Bot, CheckSquare, ChevronDown, Edit, Key, List, Loader, Plus, Square, X } from "lucide-react";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { Dispatch, ReactNode, SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { useCSVReader } from "react-papaparse";
import { Button } from "../ui/button";
import { autoNameColumn, autoTypeColumn, prepareUploadData, validateColumns } from "./typeValidation";

import { useMutateArticles } from "@/api/articles";
import { useHasProjectRole } from "@/api/project";
import { useMultimediaConcatenatedList } from "@/api/multimedia";
import { splitIntoBatches } from "@/api/util";
import { toast } from "sonner";
import { CreateFieldInfoDialog, CreateFieldNameInput, CreateFieldSelectType } from "../Fields/CreateField";
import { Checkbox } from "../ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { DynamicIcon } from "../ui/dynamic-icon";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import SimpleTooltip from "../ui/simple-tooltip";
import { Label } from "../ui/label";
import { Progress } from "../ui/progress";
import { Loading } from "../ui/loading";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
}

export type jsType = string | number | boolean;
export type Status = "Validating" | "Ready" | "Not used" | "Type not set" | "Type invalid" | "Type warning";
interface UploadStatus {
  operation: UploadOperation;
  status: "idle" | "uploading" | "success" | "error";
  error: string | null;
  batch_index: number;
  batches: {
    documents: Record<string, any>[];
    fields?: Record<string, UpdateAmcatField>;
    operation: UploadOperation;
  }[];
  successes: number;
  failures: number;
}

export interface Column {
  name: string;
  field: string | null;
  type: AmcatFieldType | null;
  elastic_type: AmcatElasticFieldType | null;
  status: Status;
  exists: boolean;
  typeWarning?: string;
  identifier?: boolean;
  invalidExamples?: string[];
}

// TODO: Operation is currently not working (always uses index)

export default function Upload({ user, projectId }: Props) {
  const { data: fields, isLoading: fieldsLoading } = useFields(user, projectId);
  const isAdmin = useHasProjectRole(user, projectId, "ADMIN");
  const [data, setData] = useState<Record<string, jsType>[]>([]);
  const [columns, setColumns] = useState<Column[]>([]);
  const { mutateAsync: mutateArticles } = useMutateArticles(user, projectId);
  const unusedFields = useMemo(() => {
    if (!fields) return [];
    return fields.filter((f) => !columns.find((c) => c.field === f.name));
  }, [fields, columns]);
  const [validating, setValidating] = useState(false);
  const [operation, setOperation] = useState<UploadOperation>("create");
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>({
    operation,
    status: "idle",
    error: null,
    batch_index: 0,
    batches: [],
    successes: 0,
    failures: 0,
  });
  const [createColumn, setCreateColumn] = useState<Column | null>(null);
  const [noIdentifierWarning, setNoIdentifierWarning] = useState(false);

  const multimediaPrefixes = useMemo(() => {
    // If there are multimedia columns, grab all prefixes from the keys
    // (not external urls). This is used to fetch the list of existing
    // multimedia items, but only within the specified prefixes (aka directories)
    const prefixes = new Set<string>();
    for (const column of columns) {
      if (column.type === "image" || column.type === "video") {
        for (const row of data) {
          const value = String(row[column.name]);
          if (/^https?:\/\//.test(value)) continue;
          const prefix = value?.replace(/\/[^/]*$/, "/");
          prefixes.add(prefix);
        }
      }
    }
    return Array.from(prefixes);
  }, [data, columns]);
  const multimedia = useMultimediaConcatenatedList(user, projectId, multimediaPrefixes);

  useEffect(() => {
    const needsValidation = columns.filter((c) => c.status === "Validating");
    if (needsValidation.length === 0) {
      setValidating(false);
      return;
    }
    setValidating(true);

    // need to wait until multimedia is collected to perform validation
    if (multimediaPrefixes.length > 0 && !multimedia) return;

    validateColumns(columns, data, multimedia).then((newColumns) => {
      setColumns(newColumns);
    });
  }, [columns, data, multimedia, multimediaPrefixes]);

  useEffect(() => {
    // upload batches
    if (uploadStatus.status !== "uploading") return;
    const batch = uploadStatus.batches[uploadStatus.batch_index];
    mutateArticles(batch)
      .then((result) => {
        if (uploadStatus.batch_index === uploadStatus.batches.length - 1) {
          setUploadStatus((uploadStatus) => ({ ...uploadStatus, status: "success" }));
          const operationMessage = operation === "index" ? "created or updated" : "created";
          setData([]);
          setColumns([]);
          setCreateColumn(null);
          toast.success(
            `Upload complete: ${operationMessage} ${uploadStatus.successes + result.successes} / ${
              uploadStatus.successes + result.successes + uploadStatus.failures + result.failures.length
            } documents. `,
          );
        } else {
          setUploadStatus((uploadStatus) => ({
            ...uploadStatus,
            batch_index: uploadStatus.batch_index + 1,
            successes: uploadStatus.successes + result.successes,
            failures: uploadStatus.failures + result.failures.length,
          }));
        }
      })
      .catch((e) => {
        setUploadStatus((uploadStatus) => ({ ...uploadStatus, status: "error", error: e.message }));
        // toast.error("Upload failed");
      });
  }, [uploadStatus]);

  const duplicates = useMemo(() => hasDuplicates(data, columns), [data, columns]);
  const nonePending = columns.length > 0 && columns.every((c) => !["Validating", "Type not set"].includes(c.status));
  const ready = !duplicates && nonePending && columns.some((c) => c.status === "Ready" || c.status === "Type invalid");
  const warn = columns.some((c) => c.status === "Type invalid");

  async function startUpload() {
    if (!ready) return;
    const batches = splitIntoBatches(data, 100);
    setUploadStatus({
      operation,
      status: "uploading",
      error: null,
      batch_index: 0,
      batches: batches.map((batch) => prepareUploadData(batch, columns, operation, multimedia)),
      successes: 0,
      failures: 0,
    });
  }

  function setColumn(column: Column) {
    const newColumn = { ...column };

    if (!column.exists && column.field !== null) {
      const uniqueFields = new Set(columns.filter((c) => c.field !== newColumn.field).map((c) => c.field));
      fields?.forEach((f) => uniqueFields.add(f.name));
      let suffix = "";
      let i = 2;
      while (uniqueFields.has(`${column.field}${suffix}`)) {
        suffix = suffix + String(i++);
      }
      newColumn.field = `${column.field}${suffix}`;
    }
    setColumns(columns.map((c) => (c.name === newColumn.name ? newColumn : c)));
  }

  function onUpload() {
    if (!fields) return;
    const allNew = columns.every((c) => !c.exists);
    const noIdentifiers = columns.every((c) => !c.identifier);
    if (allNew && noIdentifiers) {
      setNoIdentifierWarning(true);
    } else {
      startUpload();
    }
  }

  function onIgnoreNoIdentifierWarning() {
    setNoIdentifierWarning(false);
    startUpload();
  }

  function suggestAmcatFields() {
    const newColumns: Column[] = columns.map((column) => {
      if (!column.exists && !column.type && !column.field) {
        return autoTypeColumn(data, column.name);
      }
      return column;
    });
    setColumns(newColumns);
  }

  if (fieldsLoading) return <Loading />;
  if (!fields) return null;

  if (uploadStatus.status === "uploading")
    return <UploadScreen uploadStatus={uploadStatus} setUploadStatus={setUploadStatus} />;

  return (
    <div className="mb-12 flex flex-col gap-4">
      <CSVUploader fields={fields} setData={setData} setColumns={setColumns} />
      <div className={`flex flex-col gap-8 ${data.length === 0 ? "hidden" : ""}`}>
        <Button
          variant="outline"
          className="ml-auto flex items-center justify-center gap-2"
          onClick={suggestAmcatFields}
          disabled={!columns.some((column) => !column.field)}
        >
          <Bot className="h-6 w-6 flex-shrink-0" /> Suggest new fields for unused columns
        </Button>
        <UploadTable
          columns={columns}
          data={data}
          unusedFields={unusedFields}
          setColumn={setColumn}
          createColumn={createColumn}
          setCreateColumn={setCreateColumn}
        />
        <div className="prose max-w-none rounded border p-6 dark:prose-invert">
          <h3>Confirm upload</h3>
          <UnusedFields columns={columns} fields={fields} />
          <div className="flex items-center">
            <Button disabled={!ready} onClick={onUpload}>
              Upload {data.length || ""} documents
            </Button>
            <IdentifiersWarningDialog
              noIdentifierWarning={noIdentifierWarning}
              setNoIdentifierWarning={setNoIdentifierWarning}
              onIgnoreNoIdentifierWarning={onIgnoreNoIdentifierWarning}
            />
            <UploadOptions isAdmin={!!isAdmin} operation={operation} setOperation={setOperation} />

            <div className="flex flex-col gap-2">
              {warn ? (
                <div className="ml-4 flex items-center gap-2">
                  <AlertCircleIcon className="h-6 w-6 text-secondary" />
                  <div>Some field values have an invalid type. These will become missing values</div>
                </div>
              ) : null}
              {duplicates ? (
                <div className="ml-4 flex items-center gap-2">
                  <AlertCircleIcon className="h-6 w-6 text-warn" />
                  <div>Some documents have duplicate identifiers</div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
      <CreateFieldDialog
        createColumn={createColumn}
        setCreateColumn={setCreateColumn}
        setColumn={setColumn}
        disabled={validating}
        fields={fields}
      />
    </div>
  );
}

function UploadTable({
  columns,
  data,
  unusedFields,
  setColumn,
  createColumn,
  setCreateColumn,
}: {
  columns: Column[];
  data: Record<string, jsType>[];
  unusedFields: AmcatField[];
  setColumn: (column: Column) => void;
  createColumn: Column | null;
  setCreateColumn: (column: Column | null) => void;
}) {
  const [editColumn, setEditColumn] = useState<Column | null>(null);
  return (
    <Table className="table table-fixed whitespace-nowrap">
      <TableHeader>
        <TableRow className="bg-primary hover:bg-primary">
          <TableHead className="text-lg font-semibold text-primary-foreground">CSV Column</TableHead>
          <TableHead className="text-lg font-semibold text-primary-foreground">AmCAT Field</TableHead>
          <TableHead className="w-40 text-lg font-semibold text-primary-foreground"></TableHead>
          <TableHead className="text-lg font-semibold text-primary-foreground">Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {columns.map((column) => {
          return (
            <TableRow key={column.name} className="">
              <TableCell className="max-w-20 overflow-hidden text-ellipsis text-balance  bg-primary/10">
                <span title={column.name}> {column.name}</span>
              </TableCell>
              <TableCell className="overflow-hidden text-ellipsis  text-balance">
                <SelectAmcatField
                  data={data}
                  column={column}
                  unusedFields={unusedFields}
                  setColumn={setColumn}
                  createColumn={createColumn}
                  setCreateColumn={setCreateColumn}
                />
              </TableCell>
              <TableCell>
                <RemoveOrEditField
                  data={data}
                  column={column}
                  setColumn={setColumn}
                  setCreateColumn={setCreateColumn}
                />
              </TableCell>
              <TableCell className="overflow-auto text-wrap">{getUploadStatus(column, data)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

function UploadScreen({
  uploadStatus,
  setUploadStatus,
}: {
  uploadStatus: UploadStatus;
  setUploadStatus: Dispatch<SetStateAction<UploadStatus>>;
}) {
  return (
    <div className="mx-auto flex flex-col gap-4">
      <h3 className="prose-xl w-full">Uploading documents</h3>
      <div className="flex items-center gap-4">
        <div>
          <Progress value={((uploadStatus.batch_index + 1) / uploadStatus.batches.length) * 100} className="w-96" />
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex gap-2">
          <Button
            onClick={() => {
              setUploadStatus({ ...uploadStatus, status: "idle" });
            }}
          >
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

function UnusedFields({ columns, fields }: { columns: Column[]; fields: AmcatField[] }) {
  const unusedColumns = columns.filter((c) => !c.field);
  const unusedIdentifiers = fields.filter((c) => c.identifier && !columns.find((col) => col.field === c.name));
  const unusedOther = fields.filter((c) => !c.identifier && !columns.find((col) => col.field === c.name));

  function unusedDropdown({
    items,
    key,
    identifier,
    column,
  }: {
    items: AmcatField[] | Column[];
    key: string;
    identifier?: boolean;
    column?: boolean;
  }) {
    if (items.length === 0) return null;
    const what = identifier ? "identifier " : column ? "column " : "";
    function msg() {
      if (identifier) return "AmCAT identifier fields not used";
      if (column) return "CSV columns not used";
      return "AmCAT fields not used";
    }

    return (
      <div key={key} className={`${items.length > 0 ? "" : "hidden"}`}>
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-3 py-1">
            {identifier ? (
              <AlertCircleIcon className="h-6 w-6 text-warn" />
            ) : (
              <AlertCircleIcon className="h-6 w-6 text-secondary" />
            )}
            {items.length} {msg()}
            <ChevronDown className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            {items.map((field) => (
              <DropdownMenuItem key={field.name} className="flex items-center gap-1">
                <DynamicIcon type={field.type} className="mr-2 h-6 w-6 flex-shrink-0" />
                {field.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    );
  }

  return (
    <div className="flex flex-col py-2">
      {unusedDropdown({ key: "unusedColumns", items: unusedColumns, column: true })}
      {unusedDropdown({ key: "unusedIdentifiers", items: unusedIdentifiers, column: true })}
      {unusedDropdown({ key: "unusedOthers", items: unusedOther, column: true })}
    </div>
  );
}

function IdentifiersWarningDialog({
  noIdentifierWarning,
  setNoIdentifierWarning,
  onIgnoreNoIdentifierWarning,
}: {
  noIdentifierWarning: boolean;
  setNoIdentifierWarning: Dispatch<SetStateAction<boolean>>;
  onIgnoreNoIdentifierWarning: () => void;
}) {
  return (
    <Dialog open={noIdentifierWarning} onOpenChange={() => setNoIdentifierWarning(false)}>
      <DialogContent>
        <DialogHeader className="text-lg font-bold">Are you sure you don't need identifiers?</DialogHeader>
        <p>
          If you select one or multiple identifiers (by clicking on the key button), they will be used to uniquely
          identify documents. It can be a unique field like a <b>URL</b>, but also a combination of fields like{" "}
          <b>author + timestamp</b>. Identifiers prevent accidentally uploading duplicate documents, and you can use
          them to update existing documents.
        </p>
        <p>
          If no identifiers are specified before uploading the first data, you will not be able to add them later. Each
          document will then get a unique ID, and you will only be able to update documents by this internal ID.
        </p>
        <div className="mt-5 flex justify-end gap-3">
          <Button variant="outline" onClick={() => setNoIdentifierWarning(false)}>
            Cancel
          </Button>
          <Button onClick={onIgnoreNoIdentifierWarning}>Upload without identifiers</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function UploadOptions({
  isAdmin,
  operation,
  setOperation,
}: {
  isAdmin: boolean;
  operation: UploadOperation;
  setOperation: (operation: UploadOperation) => void;
}) {
  function renderOperationLabel(operation: UploadOperation) {
    switch (operation) {
      case "create":
        return "Create";
      case "update":
        return "Create or update";
      case "index":
        return "Create or replace";
    }
  }

  return (
    <div className="ml-3 flex">
      <div className="flex items-center gap-4">
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 rounded p-2">
            {renderOperationLabel(operation)}
            <ChevronDown className="h-5 w-5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" className="max-w-md">
            <DropdownMenuLabel>Upload operation</DropdownMenuLabel>
            <DropdownMenuItem
              onClick={() => setOperation("create")}
              className="flex-col items-start justify-start gap-1"
            >
              <span className="">Create</span>
              <div className=" font-light text-foreground/60">
                Only create new documents. If an identifier already exists, do not upload the document.
              </div>
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={!isAdmin}
              onClick={() => setOperation("update")}
              className="flex-col items-start justify-start gap-1"
            >
              <span className="">
                Create or update{" "}
                {isAdmin ? "" : <span className="rounded bg-warn px-1 text-warn-foreground">admin only</span>}
              </span>
              <span className="font-light text-foreground/60">Create new documents and update existing ones </span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

function getUploadStatus(column: Column, data: Record<string, jsType>[]) {
  let icon: ReactNode;
  let text = String(column.status);

  switch (column.status) {
    case "Ready":
      icon = <CheckSquare className="h-6 w-6 flex-shrink-0 text-check" />;
      break;
    case "Validating":
      icon = <Loader className="h-6 w-6 flex-shrink-0 animate-spin" />;
      break;
    case "Type not set":
      icon = <Square className="h-6 w-6 flex-shrink-0 text-warn" />;
      break;
    case "Type invalid":
      icon = <AlertCircleIcon className="h-6 w-6 flex-shrink-0 text-warn" />;
      text = column.typeWarning || "Type invalid";
      break;
    case "Type warning":
      icon = <AlertCircleIcon className="h-6 w-6 flex-shrink-0 text-secondary" />;
      text = column.typeWarning || "Type warning";
      break;
    default:
      icon = <Square className="h-6 w-6 flex-shrink-0 text-secondary" />;
  }

  let examples: ReactNode = null;
  if (column.invalidExamples) {
    examples = (
      <TooltipContent className="bg-background">
        <div className="flex max-h-56 flex-col gap-2 overflow-auto">
          <div className="font-bold">Examples of invalid values</div>
          <div className="flex flex-col gap-1 ">
            {column.invalidExamples.map((ex) => (
              <div key={ex} className="max-w-[80vw] overflow-hidden text-ellipsis text-foreground/60">
                {ex}
              </div>
            ))}
          </div>
        </div>
      </TooltipContent>
    );
  }

  return (
    <div className="flex items-center gap-3">
      {icon}
      <Tooltip>
        <TooltipTrigger className="text-left">{text}</TooltipTrigger>
        {examples}
      </Tooltip>
    </div>
  );
}

interface RemoveOrEditProps {
  data: Record<string, jsType>[];
  column: Column;
  setColumn: (column: Column) => void;
  setCreateColumn: (column: Column | null) => void;
}

function RemoveOrEditField({ data, column, setColumn, setCreateColumn }: RemoveOrEditProps) {
  const notused = column.status === "Not used";

  if (!column.field) return null;

  return (
    <div className="flex items-center gap-1">
      <Button
        variant={"ghost"}
        size="icon"
        className={column.exists || notused ? "invisible" : ""}
        disabled={column.exists || notused}
        onClick={() => {
          setCreateColumn(column);
        }}
      >
        <Edit className="h-5 w-5 flex-shrink-0" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className={notused ? "invisible" : ""}
        disabled={notused}
        onClick={() =>
          setColumn({
            name: column.name,
            field: null,
            type: null,
            elastic_type: null,
            status: "Not used",
            exists: false,
          })
        }
      >
        <X className="h-6 w-6 text-foreground/60" />
      </Button>
    </div>
  );
}

function SelectAmcatField({
  data,
  column,
  setColumn,
  unusedFields,
  createColumn,
  setCreateColumn,
}: {
  data: Record<string, jsType>[];
  column: Column;
  setColumn: (column: Column) => void;
  unusedFields: AmcatField[];
  createColumn: Column | null;
  setCreateColumn: (column: Column | null) => void;
}) {
  if (!column) return null;

  if (column.type) {
    return (
      <div className="flex items-center gap-3 rounded p-2 pl-0">
        <DynamicIcon type={column.type} className="h-6 w-6 flex-shrink-0" />
        <div className="py-0 text-left leading-5">
          <div className="break-all font-bold text-primary">{column.field}</div>
          <div className="text-sm font-light text-foreground/60 ">{column.type}</div>
        </div>
      </div>
    );
  }

  // if (unusedFields.length === 0) return <div></div>;

  return (
    <div className="flex items-center gap-2">
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger className={`flex items-center gap-3 rounded p-2 pl-0 `}>
          Assign to field
          <ChevronDown className={` h-5 w-5 ${!column.field ? "" : "hidden"}`} />
        </DropdownMenuTrigger>
        <DropdownMenuContent className="max-h-[80vh] overflow-auto">
          <DropdownMenuItem
            onClick={() => setCreateColumn(autoTypeColumn(data, column.name))}
            className="flex items-center gap-2"
          >
            <Plus className="h-6 w-6 flex-shrink-0" /> Create new field
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => setColumn(autoTypeColumn(data, column.name))}
            className="flex items-center gap-2"
          >
            <Bot className="h-6 w-6 flex-shrink-0" /> Suggest new field
          </DropdownMenuItem>
          <DropdownMenuGroup className={unusedFields.length > 0 ? "" : "hidden"}>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Use existing field</DropdownMenuLabel>
            {unusedFields.map((field) => {
              return (
                <DropdownMenuItem
                  key={field.name}
                  className="flex items-center gap-2"
                  onClick={() =>
                    setColumn({
                      ...column,
                      field: field.name,
                      type: field.type,
                      elastic_type: field.elastic_type,
                      status: "Validating",
                      exists: true,
                    })
                  }
                >
                  <DynamicIcon type={field.type} className="h-6 w-6 flex-shrink-0" /> &nbsp;
                  <span title={field.name} className="max-w-80 overflow-hidden text-ellipsis">
                    {field.name}
                  </span>
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function CreateFieldDialog({
  createColumn,
  setCreateColumn,
  setColumn,
  disabled,
  fields,
}: {
  createColumn: Column | null;
  setCreateColumn: (column: Column | null) => void;
  setColumn: (column: Column) => void;
  disabled?: boolean;
  fields: AmcatField[];
}) {
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(true);
  }, [createColumn]);

  if (!createColumn || disabled) return null;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="sr-only">Create new field</DialogTitle>
          <DialogDescription className="sr-only">Create new project field</DialogDescription>
          <div className="text-lg font-bold">Create new field</div>
          {/* <p className="text-sm">
            This creates a new project field. Make sure to pick a suitable field type, since you won't be able to change
            this after the data has been uploaded.
          </p> */}
        </DialogHeader>
        <div className="flex flex-col gap-4 overflow-auto p-1">
          <div className="grid grid-cols-1 items-end gap-4 sm:grid-cols-[1fr,10rem]">
            <CreateFieldNameInput
              name={createColumn.field || undefined}
              setName={(name) => setCreateColumn({ ...createColumn, field: name })}
              setError={setError}
              fields={fields}
            />
            <CreateFieldSelectType
              type={createColumn.type}
              setType={(type) => setCreateColumn({ ...createColumn, status: "Validating", type })}
            />
          </div>
          <div className=" flex items-center gap-3 ">
            <Key className="h-6 w-6" />
            <label className="">Use as identifier</label>
            <Checkbox
              className="ml-[2px] h-5 w-5"
              checked={createColumn.identifier}
              onCheckedChange={() => setCreateColumn({ ...createColumn, identifier: !createColumn.identifier })}
            >
              Field exists
            </Checkbox>
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <CreateFieldInfoDialog />
          {error ? (
            <div className="ml-auto max-w-64 overflow-hidden text-ellipsis text-sm text-destructive">{error}</div>
          ) : null}
          <div className="ml-auto flex gap-2">
            <Button
              disabled={!createColumn.field || !createColumn.type || !!error}
              onClick={() => {
                if (!error) setColumn(createColumn);
                setCreateColumn(null);
              }}
            >
              Create
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function CSVUploader({
  fields,
  setData,
  setColumns,
}: {
  fields: AmcatField[];
  setData: Dispatch<SetStateAction<Record<string, jsType>[]>>;
  setColumns: Dispatch<SetStateAction<Column[]>>;
}) {
  const { CSVReader } = useCSVReader();
  const fileRef = useRef(undefined);
  const [zoneHover, setZoneHover] = useState(false);

  return (
    <div className="flex">
      <CSVReader
        skipEmptyLines
        dynamicTyping
        onUploadAccepted={(res: any) => {
          setZoneHover(false);
          prepareData({ importedData: res.data, fields, setData, setColumns });
        }}
        onDragOver={(e: DragEvent) => {
          e.preventDefault();
          setZoneHover(true);
        }}
        onDragLeave={(e: DragEvent) => {
          e.preventDefault();
          setZoneHover(false);
        }}
      >
        {({ getRootProps, acceptedFile, ProgressBar, getRemoveFileProps }: any) => {
          if (acceptedFile)
            return (
              <div className="flex w-full items-center justify-end gap-2">
                {/* <div className="ml-auto rounded-lg bg-secondary px-3 py-2 text-center text-secondary-foreground">
                  {acceptedFile && acceptedFile.name}
                </div> */}
                <Button
                  className="px-1"
                  variant="ghost"
                  ref={fileRef}
                  {...getRemoveFileProps()}
                  onClick={(e) => {
                    setColumns([]);
                    setData([]);
                    getRemoveFileProps().onClick(e);
                  }}
                >
                  <X className="h-8 w-8" />
                </Button>
              </div>
            );

          return (
            <div className="w-full">
              <Button
                variant="outline"
                className={`${zoneHover ? "bg-primary/30" : ""} text-md w-full flex-auto border-dotted bg-primary/10 px-10 py-14 hover:bg-primary/20 `}
                {...getRootProps()}
              >
                Click to upload a CSV file, or drag and drop it here
              </Button>
              <ProgressBar />
            </div>
          );
        }}
      </CSVReader>
    </div>
  );
}

function prepareData({
  importedData,
  fields,
  setData,
  setColumns,
}: {
  importedData: jsType[][];
  fields: AmcatField[];
  setData: Dispatch<SetStateAction<Record<string, jsType>[]>>;
  setColumns: Dispatch<SetStateAction<Column[]>>;
}) {
  const usedFields = new Set<string>();

  const columns = importedData[0].map((column): Column => {
    const name = String(column);
    const field = fields.find((f) => {
      if (usedFields.has(f.name)) return false;
      return autoNameColumn(name) === f.name;
    });
    if (!field) return { name, field: null, type: null, elastic_type: null, status: "Not used", exists: false };

    usedFields.add(field.name);
    return {
      name,
      field: field.name,
      type: field.type,
      elastic_type: field.elastic_type,
      status: "Validating",
      identifier: field.identifier,
      exists: true,
    };
  });

  const data = importedData
    .slice(1)
    .map((row) => {
      const obj: Record<string, jsType> = {};
      row.forEach((cell, i) => {
        obj[columns[i].name] = cell;
      });
      return obj;
    })
    .filter((row) => {
      // remove row if all cells are empty (because papaparse  sometimes fails to remove them)
      return Object.values(row).some((cell) => cell !== null && cell !== undefined && cell !== "");
    });

  setData(data);
  setColumns(columns.filter((column) => !!column.name));
}

function hasDuplicates(data: Record<string, jsType>[], columns: Column[]) {
  let identifiers = columns.filter((c) => c.identifier).map((c) => c.name);
  if (identifiers.length === 0) identifiers = columns.map((c) => c.name);
  const ids = data.map((doc) => {
    const idCols = identifiers.map((id) => doc[id]);
    return JSON.stringify(idCols);
  });
  const uniqueIds = new Set(ids);
  return ids.length !== uniqueIds.size;
}

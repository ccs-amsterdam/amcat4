import { useFields } from "@/api/fields";
import {
  AmcatElasticFieldType,
  AmcatField,
  AmcatFieldType,
  AmcatProjectId,
  UpdateAmcatField,
  UploadOperation,
} from "@/interfaces";
import { AlertCircleIcon, ChevronDown, Key, Loader, Lock, RotateCcw } from "lucide-react";
import { InfoBox } from "../ui/info-box";
import { ZipUploader } from "./ZipUploader";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { Dispatch, SetStateAction, useEffect, useMemo, useState } from "react";
import { Button } from "../ui/button";
import { autoNameColumn, autoTypeColumn, prepareUploadData, validateColumns } from "./typeValidation";

import { useMutateArticles } from "@/api/articles";
import { useHasProjectRole } from "@/api/project";
import { useMultimediaConcatenatedList } from "@/api/multimedia";
import { splitIntoBatches } from "@/api/util";
import { Link } from "@tanstack/react-router";
import { CreateFieldSelectType } from "../Fields/CreateField";
import { Input } from "../ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { DynamicIcon } from "../ui/dynamic-icon";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import SimpleTooltip from "../ui/simple-tooltip";
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
  errorDetail?: unknown;
  batch_index: number;
  batches: {
    documents: Record<string, any>[];
    fields?: Record<string, UpdateAmcatField>;
    operation: UploadOperation;
  }[];
  successes: number;
  failures: number;
  failureReasons: string[];
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
  const [_validating, setValidating] = useState(false);
  const [operation, setOperation] = useState<UploadOperation>("update");
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>({
    operation,
    status: "idle",
    error: null,
    batch_index: 0,
    batches: [],
    successes: 0,
    failures: 0,
    failureReasons: [],
  });
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
    const isLastBatch = uploadStatus.batch_index === uploadStatus.batches.length - 1;
    const batch = { ...uploadStatus.batches[uploadStatus.batch_index], refresh: isLastBatch };
    mutateArticles(batch)
      .then((result) => {
        if (isLastBatch) {
          setUploadStatus((prev) => ({
            ...prev,
            status: "success",
            successes: prev.successes + result.successes,
            failures: prev.failures + result.failures.length,
            failureReasons: [...prev.failureReasons, ...result.failures],
          }));
        } else {
          setUploadStatus((uploadStatus) => ({
            ...uploadStatus,
            batch_index: uploadStatus.batch_index + 1,
            successes: uploadStatus.successes + result.successes,
            failures: uploadStatus.failures + result.failures.length,
            failureReasons: [...uploadStatus.failureReasons, ...result.failures],
          }));
        }
      })
      .catch((e) => {
        setUploadStatus((s) => ({ ...s, status: "error", error: e.message, errorDetail: e.response?.data }));
      });
  }, [uploadStatus]);

  const duplicates = useMemo(() => hasDuplicates(data, columns), [data, columns]);
  const nonePending = columns.length > 0 && columns.every((c) => !["Validating", "Type not set"].includes(c.status));
  const hasInvalid = columns.some((c) => c.status === "Type invalid");
  const ready = !duplicates && nonePending && !hasInvalid && columns.some((c) => c.status === "Ready" || c.status === "Type warning");
  const hasIdentifiers = useMemo(() => columns.some((c) => c.identifier), [columns]);

  useEffect(() => {
    if (!hasIdentifiers) setOperation("create");
  }, [hasIdentifiers]);

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
      failureReasons: [],
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

  function resetUpload() {
    setData([]);
    setColumns([]);
    setUploadStatus((prev) => ({ ...prev, status: "idle" }));
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

if (fieldsLoading) return <Loading />;
  if (!fields) return null;

  return (
    <div className="mb-12 flex flex-col gap-4">
      {data.length === 0 ? (
        <ZipUploader fields={fields} setData={setData} setColumns={setColumns} />
      ) : (
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground" onClick={resetUpload}>
            <RotateCcw className="h-3.5 w-3.5" />
            Change file
          </Button>
        </div>
      )}
      <div className={`flex flex-col gap-8 ${data.length === 0 ? "hidden" : ""}`}>
        {columns.some((c) => c.field === null) && (
          <div className="flex justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setColumns(columns.map((c) => c.field === null ? autoTypeColumn(data, c.name) : c))}
            >
              Include all fields
            </Button>
          </div>
        )}
        <UploadTable columns={columns} data={data} fields={fields} setColumn={setColumn} />
        <div className="prose max-w-none rounded border p-6 dark:prose-invert">
          <h3>Confirm upload</h3>
          <UnusedFields columns={columns} fields={fields} />
          {hasInvalid && (() => {
            const n = columns.filter((c) => c.status === "Type invalid").length;
            return <p className="text-sm text-destructive">{n} field{n !== 1 ? "s" : ""} failed to validate</p>;
          })()}
          <div className="flex items-center">
            <Button disabled={!ready} onClick={onUpload}>
              Upload {data.length || ""} documents
            </Button>
            <IdentifiersWarningDialog
              noIdentifierWarning={noIdentifierWarning}
              setNoIdentifierWarning={setNoIdentifierWarning}
              onIgnoreNoIdentifierWarning={onIgnoreNoIdentifierWarning}
            />
            <UploadOptions isAdmin={!!isAdmin} operation={operation} setOperation={setOperation} hasIdentifiers={hasIdentifiers} />

            <div className="flex flex-col gap-2">
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
      <UploadDialog uploadStatus={uploadStatus} setUploadStatus={setUploadStatus} projectId={projectId} onUploadMore={resetUpload} />
      <UploadInfoBox />
    </div>
  );
}

function UploadTable({
  columns,
  data,
  fields,
  setColumn,
}: {
  columns: Column[];
  data: Record<string, jsType>[];
  fields: AmcatField[];
  setColumn: (column: Column) => void;
}) {
  return (
    <div className="border-t text-sm">
      <div className="grid grid-cols-[1fr_7rem_1fr_10rem_1.5rem] gap-x-3 border-b bg-muted/50 px-3 py-1.5 text-xs font-medium text-muted-foreground">
        <span>CSV column</span>
        <span>Action</span>
        <span>AmCAT field</span>
        <span>Type</span>
        <span></span>
      </div>
      {columns.map((column) => (
        <UploadColumnRow
          key={column.name}
          column={column}
          columns={columns}
          data={data}
          fields={fields}
          setColumn={setColumn}
        />
      ))}
    </div>
  );
}

type ColumnAction = "new" | "existing" | "exclude";

function UploadColumnRow({
  column,
  columns,
  data,
  fields,
  setColumn,
}: {
  column: Column;
  columns: Column[];
  data: Record<string, jsType>[];
  fields: AmcatField[];
  setColumn: (column: Column) => void;
}) {
  const action: ColumnAction = column.field === null ? "exclude" : column.exists ? "existing" : "new";

  const availableFields = fields.filter(
    (f) => !columns.some((c) => c.field === f.name && c.name !== column.name),
  );

  function onActionChange(newAction: ColumnAction) {
    if (newAction === "new") {
      setColumn(autoTypeColumn(data, column.name));
    } else if (newAction === "existing") {
      const first = availableFields[0];
      if (first)
        setColumn({
          ...column,
          field: first.name,
          type: first.type,
          elastic_type: first.elastic_type,
          status: "Validating",
          exists: true,
          identifier: first.identifier,
        });
    } else {
      setColumn({ name: column.name, field: null, type: null, elastic_type: null, status: "Not used", exists: false });
    }
  }

  return (
    <div
      className={`grid grid-cols-[1fr_7rem_1fr_10rem_1.5rem] items-center gap-x-3 border-b px-3 py-1.5 ${action === "exclude" ? "opacity-40" : ""}`}
    >
      {/* CSV column name */}
      <div className="overflow-hidden text-ellipsis font-mono text-xs" title={column.name}>
        {column.name}
      </div>

      {/* Action */}
      <select
        value={action}
        onChange={(e) => onActionChange(e.target.value as ColumnAction)}
        className="h-7 rounded border border-input bg-background px-2 text-xs"
      >
        <option value="new">New field</option>
        {availableFields.length > 0 && <option value="existing">Existing field</option>}
        <option value="exclude">Exclude</option>
      </select>

      {/* Target field */}
      {action === "new" ? (
        <Input
          className="h-7 text-xs"
          value={column.field ?? ""}
          placeholder={autoNameColumn(column.name)}
          onChange={(e) =>
            setColumn({ ...column, field: e.target.value || autoNameColumn(column.name), status: "Validating" })
          }
        />
      ) : action === "existing" ? (
        <select
          value={column.field ?? ""}
          onChange={(e) => {
            const f = fields.find((f) => f.name === e.target.value);
            if (f)
              setColumn({
                ...column,
                field: f.name,
                type: f.type,
                elastic_type: f.elastic_type,
                status: "Validating",
                exists: true,
                identifier: f.identifier,
              });
          }}
          className="h-7 rounded border border-input bg-background px-2 text-xs"
        >
          {availableFields.map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
      ) : (
        <span className="text-xs text-muted-foreground">—</span>
      )}

      {/* Type + inline warning */}
      {action === "new" ? (
        <div className="flex items-center gap-1">
          <CreateFieldSelectType
            type={column.type}
            setType={(type) => setColumn({ ...column, type, status: "Validating" })}
          />
          {getTypeWarningIndicator(column)}
        </div>
      ) : action === "existing" ? (
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Lock className="h-3 w-3 shrink-0" />
          {column.type}
          {getTypeWarningIndicator(column)}
        </div>
      ) : (
        <span />
      )}

      {/* Identifier toggle */}
      {action === "new" ? (
        <SimpleTooltip text="Use as document identifier">
          <Button
            variant="ghost"
            size="icon"
            className={`h-6 w-6 ${column.identifier ? "" : "opacity-30"}`}
            onClick={() => setColumn({ ...column, identifier: !column.identifier })}
          >
            <Key className="h-4 w-4" />
          </Button>
        </SimpleTooltip>
      ) : (
        <span />
      )}
    </div>
  );
}

function UploadDialog({
  uploadStatus,
  setUploadStatus,
  projectId,
  onUploadMore,
}: {
  uploadStatus: UploadStatus;
  setUploadStatus: Dispatch<SetStateAction<UploadStatus>>;
  projectId: AmcatProjectId;
  onUploadMore: () => void;
}) {
  const isUploading = uploadStatus.status === "uploading";
  const isSuccess = uploadStatus.status === "success";
  const isError = uploadStatus.status === "error";
  const open = isUploading || isSuccess || isError;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !isUploading && onUploadMore()}>
      <DialogContent hideClose={isUploading}>
        <DialogHeader>
          <DialogTitle>
            {isUploading ? "Uploading documents" : isSuccess ? "Upload complete" : "Upload failed"}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {isUploading ? "Upload in progress" : isSuccess ? "Upload result" : "Upload error"}
          </DialogDescription>
        </DialogHeader>
        {isUploading && (
          <div className="flex flex-col gap-4">
            <Progress value={((uploadStatus.batch_index + 1) / uploadStatus.batches.length) * 100} />
            <Button
              variant="outline"
              className="w-fit"
              onClick={() => setUploadStatus({ ...uploadStatus, status: "idle" })}
            >
              Cancel
            </Button>
          </div>
        )}
        {isSuccess && (
          <div className="flex flex-col gap-4">
            <p>
              {uploadStatus.successes} document{uploadStatus.successes !== 1 ? "s" : ""} uploaded successfully.
              {uploadStatus.failures > 0 && (
                <span className="text-destructive ml-1">
                  {uploadStatus.failures} document{uploadStatus.failures !== 1 ? "s" : ""} failed.
                </span>
              )}
            </p>
            {uploadStatus.failureReasons.length > 0 && (
              <div className="max-h-40 overflow-auto rounded border p-2 text-xs text-destructive">
                {uploadStatus.failureReasons.map((reason, i) => (
                  <div key={i} className="py-0.5">{reason}</div>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <Button asChild>
                <Link to="/projects/$project/dashboard" params={{ project: projectId }}>
                  View uploaded data
                </Link>
              </Button>
              <Button variant="outline" onClick={onUploadMore}>
                Upload more data
              </Button>
            </div>
          </div>
        )}
        {isError && (
          <div className="flex flex-col gap-4">
            <p className="text-destructive">{uploadStatus.error}</p>
            {!!uploadStatus.errorDetail && (
              <pre className="max-h-40 overflow-auto rounded border p-2 text-xs text-muted-foreground">
                {JSON.stringify(uploadStatus.errorDetail, null, 2)}
              </pre>
            )}
            <Button variant="outline" onClick={onUploadMore} className="w-fit">
              Close
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
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
    function msg() {
      if (identifier) return "identifier fields without values";
      if (column) return "CSV columns excluded";
      return "fields without values in this upload";
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
            {(items as (AmcatField | Column)[]).map((field) => (
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
      {unusedDropdown({ key: "unusedIdentifiers", items: unusedIdentifiers, identifier: true })}
      {unusedDropdown({ key: "unusedOthers", items: unusedOther })}
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
  hasIdentifiers,
}: {
  isAdmin: boolean;
  operation: UploadOperation;
  setOperation: (operation: UploadOperation) => void;
  hasIdentifiers: boolean;
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
              disabled={!isAdmin || !hasIdentifiers}
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

function getTypeWarningIndicator(column: Column) {
  if (column.status === "Validating") return <Loader className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />;
  if (column.status !== "Type invalid" && column.status !== "Type warning") return null;

  const isInvalid = column.status === "Type invalid";
  const text = column.typeWarning || column.status;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <AlertCircleIcon className={`h-3.5 w-3.5 shrink-0 ${isInvalid ? "text-warn" : "text-secondary"}`} />
      </TooltipTrigger>
      <TooltipContent className="bg-background">
        <div className="flex max-h-56 flex-col gap-2 overflow-auto">
          <div className="font-bold">{text}</div>
          {column.invalidExamples && (
            <div className="flex flex-col gap-1">
              {column.invalidExamples.map((ex) => (
                <div key={ex} className="max-w-[80vw] overflow-hidden text-ellipsis text-foreground/60">
                  {ex}
                </div>
              ))}
            </div>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}


export function prepareData({
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
  const names = importedData[0].map((column) => String(column));

  const data = importedData
    .slice(1)
    .map((row) => {
      const obj: Record<string, jsType> = {};
      row.forEach((cell, i) => {
        obj[names[i]] = cell;
      });
      return obj;
    })
    .filter((row) => {
      // remove row if all cells are empty (because papaparse  sometimes fails to remove them)
      return Object.values(row).some((cell) => cell !== null && cell !== undefined && cell !== "");
    });

  const usedFields = new Set<string>();

  const columns = names.map((name): Column => {
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

  setData(data);
  setColumns(columns.filter((column) => !!column.name));
}

function UploadInfoBox() {
  return (
    <InfoBox title="Upload reference">
      <div className="flex flex-col gap-5 text-muted-foreground">
        <p>Upload a CSV, TSV, XLSX, or ZIP file to add documents to this index. For each column, choose whether to map it to a new or existing field, or exclude it. Then select the upload operation and click Upload.</p>
        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Column actions</h4>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[7rem_1fr] gap-3">
              <b className="text-primary">New field</b>
              Creates a new field in the index. You can customize the name and type before uploading.
              <b className="text-primary">Existing field</b>
              Maps the CSV column to a field that already exists. The type is fixed and cannot be changed here.
              <b className="text-primary">Exclude</b>
              The column is ignored and not uploaded.
            </div>
          </div>
        </section>

        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Upload operation</h4>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[9rem_1fr] gap-3">
              <b className="text-primary">Create</b>
              Only adds new documents. Documents already present (matched by identifier) are skipped.
              <b className="text-primary">Create or update</b>
              Adds new documents and updates fields on existing ones. Requires admin role and at least one identifier field.
            </div>
          </div>
        </section>

        <section>
          <h4 className="mb-1.5 flex items-center gap-1.5 font-semibold text-foreground">
            <Key className="h-3.5 w-3.5" /> Identifier fields
          </h4>
          <p>
            Identifier fields act as a primary key — they uniquely identify a document and prevent duplicates. Use a
            naturally unique value such as an article URL or ID. You can combine multiple identifier fields for a
            composite key (e.g. author + timestamp).
          </p>
          <p className="mt-1.5 text-primary">
            Identifier status cannot be changed after a field is created, and identifier values cannot be updated once
            a document has been indexed.
          </p>
        </section>

        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Field types</h4>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[10rem_1fr] gap-3">
              <b className="text-primary">keyword</b>
              Short labels or categories (e.g. country, language). Searched as exact values.
              <b className="text-primary">tag</b>
              Like keyword, but a document can have multiple tags.
              <b className="text-primary">text</b>
              Longer free text (e.g. article body). Analysed word-by-word for full-text search.
              <b className="text-primary">date</b>
              Date or date/time values.
              <b className="text-primary">integer</b>
              Whole numbers without decimals.
              <b className="text-primary">number</b>
              Numeric values with decimals.
              <b className="text-primary">boolean</b>
              True or false values.
              <b className="text-primary">url / image / video / audio</b>
              Links to web pages or media files. Displayed as a clickable link or inline media.
              <b className="text-primary">object</b>
              Structured JSON objects. Not analysed or parsed by Elasticsearch.
            </div>
          </div>
        </section>
      </div>
    </InfoBox>
  );
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

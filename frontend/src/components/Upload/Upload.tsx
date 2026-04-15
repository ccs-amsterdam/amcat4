import { useFields } from "@/api/fields";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import {
  AmcatElasticFieldType,
  AmcatField,
  AmcatFieldType,
  AmcatProjectId,
  UpdateAmcatField,
  UploadOperation,
} from "@/interfaces";
import { AlertCircleIcon, ChevronDown, Key, Loader, Lock, RotateCcw } from "lucide-react";
import { Dispatch, SetStateAction, useCallback, useEffect, useMemo, useState } from "react";
import { FieldTypesSection } from "../Fields/FieldTypesSection";
import { Button } from "../ui/button";
import { InfoBox } from "../ui/info-box";
import { autoNameColumn, autoTypeColumn, prepareUploadData, validateColumns } from "./typeValidation";
import { ZipUploader } from "./ZipUploader";

import { useMutateArticles } from "@/api/articles";
import { useHasProjectRole } from "@/api/project";
import { splitIntoBatches } from "@/api/util";
import CodeExample from "@/components/CodeExample/CodeExample";
import { UploadColumn } from "@/components/CodeExample/codeGenerators";
import { Link } from "@tanstack/react-router";
import { CreateFieldSelectType } from "../Fields/CreateField";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { DynamicIcon } from "../ui/dynamic-icon";
import { Input } from "../ui/input";
import { Loading } from "../ui/loading";

import { Progress } from "../ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import SimpleTooltip from "../ui/simple-tooltip";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

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
  nameExists?: boolean;
}

export interface UploadData {
  data?: Record<string, jsType>[];
  columns?: Column[];
}

// TODO: Operation is currently not working (always uses index)

export default function Upload({ user, projectId }: Props) {
  const { data: fields, isLoading: fieldsLoading } = useFields(user, projectId);
  const isAdmin = useHasProjectRole(user, projectId, "ADMIN");
  const [data, setData] = useState<Record<string, jsType>[]>([]);
  const [columns, setColumns] = useState<Column[]>([]);
  const [fileName, setFileName] = useState("");
  const { mutateAsync: mutateArticles } = useMutateArticles(user, projectId);
  const [operation, setOperation] = useState<UploadOperation>("upsert");
  const [columnsStatus, setColumnsStatus] = useState({
    hasIdentifiers: false,
    ready: false,
    duplicates: false,
    hasInvalid: false,
    duplicateNames: 0,
    missingNames: 0,
  });
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
  const existingFields = useMemo(() => {
    return new Set((fields || []).map((f) => f.name));
  }, [fields]);

  const handleDataChange = useCallback(
    async (update: UploadData) => {
      const newData = update.data || data;
      let newColumns = update.columns || [...columns];

      // validate fields
      const needsValidation = newColumns.filter((c) => c.status === "Validating").length !== 0;
      newColumns = needsValidation ? await validateColumns(newColumns, newData) : newColumns;

      // check existing field names
      for (const column of newColumns) {
        if (!column.field || column.exists) continue;
        console.log(newColumns.filter((c) => c.field === column.field));
        column.nameExists =
          existingFields.has(column.field) || newColumns.filter((c) => c.field === column.field).length > 1;
      }

      const columnsStatus = getColumnsStatus(newData, newColumns);

      if (data !== newData) setData(newData);
      setColumns(newColumns);
      if (!columnsStatus.hasIdentifiers) setOperation("create");
      setColumnsStatus(columnsStatus);
    },
    [existingFields, data, columns],
  );

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
  }, [uploadStatus, mutateArticles]);

  const uploadColumns: UploadColumn[] = columns
    .filter((c) => c.field !== null && c.type !== null)
    .map((c) => ({
      csvName: c.name,
      fieldName: c.field!,
      fieldType: c.type!,
      identifier: !!c.identifier,
      isNew: !c.exists,
    }));

  async function startUpload() {
    if (!columnsStatus.ready) return;
    const batches = splitIntoBatches(data, 100);
    setUploadStatus({
      operation,
      status: "uploading",
      error: null,
      batch_index: 0,
      batches: batches.map((batch) => prepareUploadData(batch, columns, operation)),
      successes: 0,
      failures: 0,
      failureReasons: [],
    });
  }

  function setColumn(column: Column) {
    const newColumn = { ...column };

    // if (!column.exists && column.field !== null) {
    //   const uniqueFields = new Set(columns.filter((c) => c.field !== newColumn.field).map((c) => c.field));
    //   fields?.forEach((f) => uniqueFields.add(f.name));
    //   let suffix = "";
    //   let i = 2;
    //   while (uniqueFields.has(`${column.field}${suffix}`)) {
    //     suffix = suffix + String(i++);
    //   }
    //   newColumn.field = `${column.field}${suffix}`;
    // }
    const newColumns = columns.map((c) => (c.name === newColumn.name ? newColumn : c));
    handleDataChange({ columns: newColumns });
  }

  function resetUpload() {
    handleDataChange({ data: [], columns: [] });
    setFileName("");
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
        <ZipUploader fields={fields} handleDataChange={handleDataChange} setFileName={setFileName} />
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
              onClick={() => {
                const newColumns = columns.map((c) => (c.field === null ? autoTypeColumn(data, c.name) : c));
                handleDataChange({ columns: newColumns });
              }}
            >
              Include all fields
            </Button>
          </div>
        )}
        <UploadTable columns={columns} data={data} fields={fields} setColumn={setColumn} />
        <div className="prose max-w-none rounded border p-6 dark:prose-invert">
          <h3>Confirm upload</h3>
          <UnusedFields columns={columns} fields={fields} />
          {columnsStatus.hasInvalid &&
            (() => {
              const n = columns.filter((c) => c.status === "Type invalid").length;
              return (
                <p className="text-sm text-destructive">
                  {n} field{n !== 1 ? "s" : ""} failed to validate
                </p>
              );
            })()}
          {columnsStatus.duplicateNames ? (
            <p className="text-sm text-destructive">
              {columnsStatus.duplicateNames} duplicate name{columnsStatus.duplicateNames === 1 ? "" : "s"}
            </p>
          ) : null}
          {columnsStatus.missingNames ? (
            <p className="text-sm text-destructive">
              {columnsStatus.missingNames} missing name{columnsStatus.missingNames === 1 ? "" : "s"}
            </p>
          ) : null}
          <div className="flex items-center gap-2">
            <Button disabled={!columnsStatus.ready} onClick={onUpload}>
              Upload {data.length || ""} documents
            </Button>
            <CodeExample action="upload" projectId={projectId} uploadColumns={uploadColumns} fileName={fileName} />
            <IdentifiersWarningDialog
              noIdentifierWarning={noIdentifierWarning}
              setNoIdentifierWarning={setNoIdentifierWarning}
              onIgnoreNoIdentifierWarning={onIgnoreNoIdentifierWarning}
            />
            <UploadOptions
              isAdmin={!!isAdmin}
              operation={operation}
              setOperation={setOperation}
              hasIdentifiers={columnsStatus.hasIdentifiers}
            />

            <div className="flex flex-col gap-2">
              {columnsStatus.duplicates ? (
                <div className="ml-4 flex items-center gap-2">
                  <AlertCircleIcon className="h-6 w-6 text-warn" />
                  <div>Some documents have duplicate identifiers</div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
      <UploadDialog
        uploadStatus={uploadStatus}
        setUploadStatus={setUploadStatus}
        projectId={projectId}
        onUploadMore={resetUpload}
      />
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
      <div className="grid grid-cols-2 gap-3 border-b bg-primary/10  px-3 py-3 text-xs font-medium text-foreground md:grid-cols-[1fr,8rem,1fr,12rem,1.5rem]">
        <span>CSV column</span>
        <span>Action</span>
        <span>AmCAT field</span>
        <span>Type</span>
        <span>
          <Key className="h-5 w-5" />
        </span>
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

  const availableFields = fields.filter((f) => !columns.some((c) => c.field === f.name && c.name !== column.name));

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
      className={`grid grid-cols-2 items-center gap-x-3 gap-y-1 border-b px-3 py-1.5 md:grid-cols-[1fr,8rem,1fr,12rem,1.5rem]`}
    >
      {/* CSV column name */}
      <div className="flex items-center gap-3">
        {/*{getTypeWarningIndicator(column)}*/}
        <div className={`truncate text-xs font-light ${action === "exclude" ? "opacity-40" : ""}`} title={column.name}>
          {column.name}
        </div>
      </div>

      {/* Action */}
      <Select value={action} onValueChange={(value) => onActionChange(value as ColumnAction)}>
        <SelectTrigger className="h-7 border-none bg-primary text-xs text-primary-foreground">
          <SelectValue placeholder="Select action" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="new">New field</SelectItem>
          <SelectItem value="existing" disabled={availableFields.length === 0}>
            Existing field
          </SelectItem>
          <SelectItem value="exclude">Exclude</SelectItem>
        </SelectContent>
      </Select>

      {/* Target field */}
      {action === "new" ? (
        <div className="flex items-center gap-3">
          <Input
            className={`h-7 truncate text-xs ${column.nameExists || column.field === "" ? "bg-destructive/20" : ""}`}
            value={column.field ?? ""}
            placeholder={autoNameColumn(column.name)}
            onChange={(e) => setColumn({ ...column, field: e.target.value || "", status: "Validating" })}
          />
          {column.nameExists ? <span className="text-sm font-light text-foreground/50">duplicate</span> : null}
          {column.field === "" ? <span className="text-sm font-light text-foreground/50">missing</span> : null}
        </div>
      ) : action === "existing" ? (
        <Select
          value={column.field ?? ""}
          onValueChange={(value) => {
            const f = fields.find((f) => f.name === value);
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
        >
          <SelectTrigger className="h-7 border-none bg-foreground/10 text-xs">
            <SelectValue placeholder="Select field" />
          </SelectTrigger>
          <SelectContent>
            {availableFields.map((f) => (
              <SelectItem key={f.name} value={f.name}>
                {f.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <span className="text-xs text-muted-foreground">—</span>
      )}

      {/* Type + inline warning */}
      {action === "new" ? (
        <div className="flex items-center gap-3">
          {getTypeWarningIndicator(column)}
          <CreateFieldSelectType
            type={column.type}
            setType={(type) => setColumn({ ...column, type, status: "Validating" })}
          />
        </div>
      ) : action === "existing" ? (
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {getTypeWarningIndicator(column)}
          <Lock className="h-3 w-3 shrink-0" />
          {column.type}
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
            <Key className="h-5 w-5" />
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
                <span className="ml-1 text-destructive">
                  {uploadStatus.failures} document{uploadStatus.failures !== 1 ? "s" : ""} failed.
                </span>
              )}
            </p>
            {uploadStatus.failureReasons.length > 0 && (
              <div className="max-h-40 overflow-auto rounded border p-2 text-xs text-destructive">
                {uploadStatus.failureReasons.map((reason, i) => (
                  <div key={i} className="py-0.5">
                    {reason}
                  </div>
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
      case "upsert":
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
              onClick={() => setOperation("upsert")}
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
  if (column.status === "Validating")
    return <Loader className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />;
  if (column.status !== "Type invalid" && column.status !== "Type warning") return null;

  const isInvalid = column.status === "Type invalid";
  const text = column.typeWarning || column.status;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <AlertCircleIcon className={`h-5 w-5 shrink-0 ${isInvalid ? "text-warn" : "text-secondary"}`} />
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
  handleDataChange,
}: {
  importedData: jsType[][];
  fields: AmcatField[];
  handleDataChange: (update: UploadData) => void;
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

  handleDataChange({
    data,
    columns: columns.filter((column) => !!column.name),
  });
}

function UploadInfoBox() {
  return (
    <InfoBox title="Information on Uploading Documents" storageKey="infobox:upload">
      <div className="flex flex-col gap-5">
        <p>
          Upload documents to this project. You can upload a spreadsheet (CSV, TSV, XLSX) or a folder or zip with with
          text, PDF, or DOCX documents. After uploading the file, you can choose what to do with each field or column in
          the data before uploading.
        </p>
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
          <h4 className="mb-1.5 flex items-center gap-1.5 font-semibold text-foreground">
            <Key className="h-3.5 w-3.5" /> Identifier fields
          </h4>
          <p>
            Identifier fields act as a primary key — they uniquely identify a document and prevent duplicates. Use a
            naturally unique value such as an article URL or ID. You can combine multiple identifier fields for a
            composite key (e.g. author + timestamp).
          </p>
          <p className="mt-1.5 text-primary">
            Identifier status cannot be changed after a field is created, and identifier values cannot be updated once a
            document has been indexed.
          </p>
        </section>

        <section>
          <h4 className="mb-1.5 font-semibold text-foreground">Upload operation</h4>
          <div className="rounded-md bg-primary/10 p-3">
            <div className="grid grid-cols-[9rem_1fr] gap-3">
              <b className="text-primary">Create</b>
              Only adds new documents. Documents already present (matched by identifier) are skipped.
              <b className="text-primary">Create or update (upsert)</b>
              Adds new documents and updates fields on existing ones based on the identifier. Requires admin role and at
              least one identifier field.
            </div>
          </div>
        </section>

        <FieldTypesSection />
      </div>
    </InfoBox>
  );
}

function dataHasDuplicates(data: Record<string, jsType>[], columns: Column[]) {
  let identifiers = columns.filter((c) => c.identifier).map((c) => c.name);
  if (identifiers.length === 0) identifiers = columns.map((c) => c.name);
  const ids = data.map((doc) => {
    const idCols = identifiers.map((id) => doc[id]);
    return JSON.stringify(idCols);
  });
  const uniqueIds = new Set(ids);
  return ids.length !== uniqueIds.size;
}

function getColumnsStatus(data: Record<string, jsType>[], columns: Column[]) {
  const duplicateNames = columns.filter((c) => c.nameExists).length;
  const missingNames = columns.filter((c) => !c.field).length;

  const duplicates = dataHasDuplicates(data, columns);
  const nonePending = columns.length > 0 && columns.every((c) => !["Validating", "Type not set"].includes(c.status));
  const hasInvalid = columns.some((c) => c.status === "Type invalid");

  const ready =
    !duplicates &&
    nonePending &&
    !hasInvalid &&
    !duplicateNames &&
    !missingNames &&
    columns.some((c) => c.status === "Ready" || c.status === "Type warning");
  const hasIdentifiers = columns.some((c) => c.identifier);

  return { duplicates, hasInvalid, ready, hasIdentifiers, duplicateNames, missingNames };
}

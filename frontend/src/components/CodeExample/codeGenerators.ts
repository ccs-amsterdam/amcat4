import { AggregationOptions, AmcatFilter, AmcatFilters, AmcatProjectId, AmcatQuery, AmcatQueryTerm } from "@/interfaces";
import { FieldReindexOptions } from "@/api/query";

export interface AuthInfo {
  needsAuth: true;
  email: string;
  apiKeysUrl: string;
}

export interface SearchParams {
  serverUrl: string;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  fields?: string[];
  auth?: AuthInfo;
}

export interface DeleteParams {
  serverUrl: string;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  auth?: AuthInfo;
}

export interface AggregateParams {
  serverUrl: string;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  options: AggregationOptions;
  auth?: AuthInfo;
}

export interface FieldsParams {
  serverUrl: string;
  projectId: AmcatProjectId;
  auth?: AuthInfo;
}

export interface CreateFieldParams {
  serverUrl: string;
  projectId: AmcatProjectId;
  fieldName: string;
  fieldType: string;
  identifier: boolean;
  auth?: AuthInfo;
}

export interface UsersParams {
  serverUrl: string;
  projectId?: AmcatProjectId;
  auth?: AuthInfo;
}

export interface AddUserParams {
  serverUrl: string;
  projectId?: AmcatProjectId;
  emails: string[];
  role: string;
  auth?: AuthInfo;
}

export interface UploadColumn {
  csvName: string;
  fieldName: string;
  fieldType: string;
  identifier: boolean;
  isNew: boolean;
}

export interface UploadParams {
  serverUrl: string;
  projectId: AmcatProjectId;
  uploadColumns: UploadColumn[];
  fileName?: string;
  auth?: AuthInfo;
}

export interface CreateProjectParams {
  serverUrl: string;
  projectId: string;
  name: string;
  description: string;
  auth?: AuthInfo;
}

export interface UpdateFieldParams {
  serverUrl: string;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  field: string;
  value: string | number | boolean | null;
  auth?: AuthInfo;
}

export interface UpdateTagsParams {
  serverUrl: string;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  field: string;
  tag: string;
  action: "add" | "remove";
  auth?: AuthInfo;
}

export interface ReindexParams {
  serverUrl: string;
  sourceProjectId: AmcatProjectId;
  destProjectId: string;
  destProjectName?: string;
  destMode: "existing" | "new";
  query: AmcatQuery;
  fieldOptions: Record<string, FieldReindexOptions>;
  auth?: AuthInfo;
}

export type CodeAction =
  | { action: "search"; params: SearchParams }
  | { action: "aggregate"; params: AggregateParams }
  | { action: "fields"; params: FieldsParams }
  | { action: "create_field"; params: CreateFieldParams }
  | { action: "users"; params: UsersParams }
  | { action: "add_user"; params: AddUserParams }
  | { action: "create_project"; params: CreateProjectParams }
  | { action: "upload"; params: UploadParams }
  | { action: "delete"; params: DeleteParams }
  | { action: "update_field"; params: UpdateFieldParams }
  | { action: "update_tags"; params: UpdateTagsParams }
  | { action: "reindex"; params: ReindexParams };

// --- Python code generation ---

function pyString(s: string): string {
  return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function pyConnect(serverUrl: string, auth: AuthInfo | undefined, includeInstall: boolean): string[] {
  const lines: string[] = [];
  if (includeInstall) lines.push("# pip install amcat4py");
  lines.push("from amcat4py import AmcatClient", "");
  if (auth) {
    lines.push(`# Get your API key at: ${auth.apiKeysUrl}`);
    lines.push(`conn = AmcatClient(${pyString(serverUrl)}, api_key="your_api_key")`);
  } else {
    lines.push(`conn = AmcatClient(${pyString(serverUrl)})`);
  }
  lines.push("");
  return lines;
}

function pyFilterValue(filter: AmcatFilter): string {
  const parts: string[] = [];
  if (filter.values !== undefined) {
    const vals = filter.values.map((v) => (typeof v === "string" ? pyString(v) : String(v))).join(", ");
    parts.push(`"values": [${vals}]`);
  }
  if (filter.exists !== undefined) parts.push(`"exists": ${filter.exists ? "True" : "False"}`);
  if (filter.gte !== undefined) parts.push(`"gte": ${pyString(filter.gte)}`);
  if (filter.lte !== undefined) parts.push(`"lte": ${pyString(filter.lte)}`);
  if (filter.gt !== undefined) parts.push(`"gt": ${pyString(filter.gt)}`);
  if (filter.lt !== undefined) parts.push(`"lt": ${pyString(filter.lt)}`);
  return `{${parts.join(", ")}}`;
}

function pyFilters(filters: AmcatFilters): string {
  const entries = Object.entries(filters)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `    ${pyString(k)}: ${pyFilterValue(v)}`);
  return `{\n${entries.join(",\n")}\n}`;
}

function pyQueries(queries: AmcatQueryTerm[]): string {
  const terms = queries.map((q) => pyString(q.query));
  return `[${terms.join(", ")}]`;
}

function generatePythonSearch(params: SearchParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, fields, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));

  const hasQueries = query.queries && query.queries.length > 0;
  const hasFilters = query.filters && Object.keys(query.filters).length > 0;
  const hasFields = fields && fields.length > 0;

  const args: string[] = [`    index=${pyString(projectId)}`];
  if (hasQueries) args.push(`    queries=${pyQueries(query.queries!)}`);
  if (hasFilters) args.push(`    filters=${pyFilters(query.filters!).replace(/\n/g, "\n    ")}`);
  if (hasFields) args.push(`    fields=[${fields!.map(pyString).join(", ")}]`);

  lines.push(`results = conn.query(\n${args.join(",\n")}\n)`);

  return lines.join("\n");
}

function generatePythonDelete(params: DeleteParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));
  const idValues = query.filters?.["_id"]?.values;
  const otherFilters = query.filters
    ? Object.fromEntries(Object.entries(query.filters).filter(([k]) => k !== "_id"))
    : {};
  const hasQueries = query.queries && query.queries.length > 0;
  const hasOtherFilters = Object.keys(otherFilters).length > 0;
  const args: string[] = [`    index=${pyString(projectId)}`];
  if (idValues && idValues.length > 0)
    args.push(`    ids=[${idValues.map((v) => pyString(String(v))).join(", ")}]`);
  if (hasQueries) args.push(`    queries=${pyQueries(query.queries!)}`);
  if (hasOtherFilters) args.push(`    filters=${pyFilters(otherFilters).replace(/\n/g, "\n    ")}`);
  lines.push(`conn.delete_by_query(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

function generatePythonAggregate(params: AggregateParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, options, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));

  const hasQueries = query.queries && query.queries.length > 0;
  const hasFilters = query.filters && Object.keys(query.filters).length > 0;
  const hasMetrics = options.metrics && options.metrics.length > 0;

  const axesStr = `[${options.axes.map(pyAxis).join(", ")}]`;
  const args: string[] = [`    index=${pyString(projectId)}`, `    axes=${axesStr}`];
  if (hasQueries) args.push(`    queries=${pyQueries(query.queries!)}`);
  if (hasFilters) args.push(`    filters=${pyFilters(query.filters!).replace(/\n/g, "\n    ")}`);
  if (hasMetrics)
    args.push(
      `    metrics=[${options.metrics!.map((m) => `{"field": ${pyString(m.field)}, "function": ${pyString(m.function)}}`).join(", ")}]`,
    );

  lines.push(`results = conn.aggregate(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

function generatePythonFields(params: FieldsParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));

  lines.push(`fields = conn.get_fields(index=${pyString(projectId)})`);
  return lines.join("\n");
}

// --- R code generation ---

function rString(s: string): string {
  return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function rConnect(serverUrl: string, auth: AuthInfo | undefined, includeInstall: boolean): string[] {
  const lines: string[] = [];
  if (includeInstall)
    lines.push(`# install.packages("amcat4r", repos = c("https://cloud.r-project.org", "https://ccs-amsterdam.r-universe.dev"))`);
  lines.push(`library(amcat4r)`, "");
  if (auth) {
    lines.push(`# Get your API key at: ${auth.apiKeysUrl}`);
    lines.push(`amcat_login(${rString(serverUrl)}, api_key = "your_api_key")`);
  } else {
    lines.push(`amcat_login(${rString(serverUrl)})`);
  }
  lines.push("");
  return lines;
}

function rFilterValue(filter: AmcatFilter): string {
  const parts: string[] = [];
  if (filter.values !== undefined) {
    const vals = filter.values.map((v) => (typeof v === "string" ? rString(v) : String(v))).join(", ");
    parts.push(`values = c(${vals})`);
  }
  if (filter.exists !== undefined) parts.push(`exists = ${filter.exists ? "TRUE" : "FALSE"}`);
  if (filter.gte !== undefined) parts.push(`gte = ${rString(filter.gte)}`);
  if (filter.lte !== undefined) parts.push(`lte = ${rString(filter.lte)}`);
  if (filter.gt !== undefined) parts.push(`gt = ${rString(filter.gt)}`);
  if (filter.lt !== undefined) parts.push(`lt = ${rString(filter.lt)}`);
  return `list(${parts.join(", ")})`;
}

function rFilters(filters: AmcatFilters): string {
  const entries = Object.entries(filters)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `    ${k} = ${rFilterValue(v)}`);
  return `list(\n${entries.join(",\n")}\n  )`;
}

function generateRSearch(params: SearchParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, fields, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));

  const hasQueries = query.queries && query.queries.length > 0;
  const hasFilters = query.filters && Object.keys(query.filters).length > 0;
  const hasFields = fields && fields.length > 0;

  const args: string[] = [`  ${rString(projectId)}`];
  if (hasQueries) {
    const queryStr = query.queries!.map((q) => q.query).join(" OR ");
    args.push(`  queries = ${rString(queryStr)}`);
  }
  if (hasFilters) {
    args.push(`  filters = ${rFilters(query.filters!).replace(/\n/g, "\n  ")}`);
  }
  if (hasFields) {
    args.push(`  fields = c(${fields!.map(rString).join(", ")})`);
  }

  lines.push(`results <- query_documents(\n${args.join(",\n")}\n)`);

  return lines.join("\n");
}

function generateRDelete(params: DeleteParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));
  const idValues = query.filters?.["_id"]?.values;
  const otherFilters = query.filters
    ? Object.fromEntries(Object.entries(query.filters).filter(([k]) => k !== "_id"))
    : {};
  const hasQueries = query.queries && query.queries.length > 0;
  const hasOtherFilters = Object.keys(otherFilters).length > 0;
  const args: string[] = [`  ${rString(projectId)}`];
  if (idValues && idValues.length > 0)
    args.push(`  ids = c(${idValues.map((v) => rString(String(v))).join(", ")})`);
  if (hasQueries) {
    const queryStr = query.queries!.map((q) => q.query).join(" OR ");
    args.push(`  queries = ${rString(queryStr)}`);
  }
  if (hasOtherFilters) args.push(`  filters = ${rFilters(otherFilters).replace(/\n/g, "\n  ")}`);
  lines.push(`delete_by_query(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

function generateRAggregate(params: AggregateParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, options, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));

  const hasQueries = query.queries && query.queries.length > 0;
  const hasFilters = query.filters && Object.keys(query.filters).length > 0;
  const hasMetrics = options.metrics && options.metrics.length > 0;

  const axesStr = `list(${options.axes.map(rAxis).join(", ")})`;
  const args: string[] = [`  ${rString(projectId)}`, `  axes = ${axesStr}`];
  if (hasQueries) {
    const queryStr = query.queries!.map((q) => q.query).join(" OR ");
    args.push(`  queries = ${rString(queryStr)}`);
  }
  if (hasFilters) args.push(`  filters = ${rFilters(query.filters!).replace(/\n/g, "\n  ")}`);
  if (hasMetrics)
    args.push(
      `  metrics = list(${options.metrics!.map((m) => `list(field = ${rString(m.field)}, func = ${rString(m.function)})`).join(", ")})`,
    );

  lines.push(`results <- query_aggregate(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

function generateRFields(params: FieldsParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));

  lines.push(`fields <- get_fields(${rString(projectId)})`);
  return lines.join("\n");
}

// --- Create field code generation ---

function generatePythonCreateField(params: CreateFieldParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, fieldName, fieldType, identifier, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));

  const name = fieldName ? pyString(fieldName) : "FIELD_NAME";
  const type = fieldType ? pyString(fieldType) : "FIELD_TYPE";
  const placeholders = [!fieldName && "FIELD_NAME", !fieldType && "FIELD_TYPE"].filter(Boolean).join(" and ");
  if (placeholders) lines.push(`# Replace ${placeholders} with the desired values`);
  const fieldSpec: string[] = [`"type": ${type}`];
  if (identifier) fieldSpec.push(`"identifier": True`);
  lines.push(`conn.set_fields(\n    index=${pyString(projectId)},\n    body={${name}: {${fieldSpec.join(", ")}}}\n)`);
  return lines.join("\n");
}

function generateRCreateField(params: CreateFieldParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, fieldName, fieldType, identifier, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));

  const name = fieldName || "FIELD_NAME";
  const type = fieldType ? rString(fieldType) : "FIELD_TYPE";
  const placeholders = [!fieldName && "FIELD_NAME", !fieldType && "FIELD_TYPE"].filter(Boolean).join(" and ");
  if (placeholders) lines.push(`# Replace ${placeholders} with the desired values`);
  const fieldSpec: string[] = [`type = ${type}`];
  if (identifier) fieldSpec.push(`identifier = TRUE`);
  lines.push(`set_fields(\n  ${rString(projectId)},\n  list(${name} = list(${fieldSpec.join(", ")}))\n)`);
  return lines.join("\n");
}

// --- Users code generation ---

function generatePythonUsers(params: UsersParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));
  lines.push(projectId
    ? `users = conn.list_index_users(index=${pyString(projectId)})`
    : `users = conn.list_users()`);
  return lines.join("\n");
}

function generateRUsers(params: UsersParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));
  lines.push(projectId
    ? `users <- list_index_users(${rString(projectId)})`
    : `users <- list_users()`);
  return lines.join("\n");
}

// --- Add user code generation ---

function generatePythonAddUser(params: AddUserParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, emails, role, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));
  if (emails.length > 1) {
    const emailList = `[${emails.map(pyString).join(", ")}]`;
    if (projectId) {
      lines.push(`for email in ${emailList}:`);
      lines.push(`    conn.add_index_user(index=${pyString(projectId)}, email=email, role=${pyString(role)})`);
    } else {
      lines.push(`for email in ${emailList}:`);
      lines.push(`    conn.create_user(email=email, role=${pyString(role)})`);
    }
  } else {
    const email = emails[0] ? pyString(emails[0]) : "EMAIL";
    if (!emails[0]) lines.push(`# Replace EMAIL with the desired email address`);
    if (projectId) {
      lines.push(`conn.add_index_user(index=${pyString(projectId)}, email=${email}, role=${pyString(role)})`);
    } else {
      lines.push(`conn.create_user(email=${email}, role=${pyString(role)})`);
    }
  }
  return lines.join("\n");
}

function generateRAddUser(params: AddUserParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, emails, role, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));
  if (emails.length > 1) {
    const emailList = `c(${emails.map(rString).join(", ")})`;
    if (projectId) {
      lines.push(`for (email in ${emailList})`);
      lines.push(`  add_index_user(${rString(projectId)}, email, ${rString(role)})`);
    } else {
      lines.push(`for (email in ${emailList})`);
      lines.push(`  create_user(email, ${rString(role)})`);
    }
  } else {
    const email = emails[0] ? rString(emails[0]) : "EMAIL";
    if (!emails[0]) lines.push(`# Replace EMAIL with the desired email address`);
    if (projectId) {
      lines.push(`add_index_user(${rString(projectId)}, ${email}, ${rString(role)})`);
    } else {
      lines.push(`create_user(${email}, ${rString(role)})`);
    }
  }
  return lines.join("\n");
}

// --- Upload documents code generation ---

function fileExt(fileName: string | undefined): string {
  return fileName?.toLowerCase().match(/\.[^.]+$/)?.[0] ?? "";
}

function pyReadFile(fileName: string | undefined): string {
  const name = fileName ? pyString(fileName) : '"your_file.csv"';
  const ext = fileExt(fileName);
  if (ext === ".tsv") return `pd.read_csv(${name}, sep="\\t")`;
  if ([".xlsx", ".xls", ".xlsm", ".ods"].includes(ext)) return `pd.read_excel(${name})`;
  return `pd.read_csv(${name})`;
}

function rReadFile(fileName: string | undefined): string {
  const name = fileName ? rString(fileName) : '"your_file.csv"';
  const ext = fileExt(fileName);
  if (ext === ".tsv") return `read_tsv(${name})`;
  if ([".xlsx", ".xls", ".xlsm", ".ods"].includes(ext)) return `read_excel(${name})`;
  return `read_csv(${name})`;
}

function generatePythonUpload(params: UploadParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, uploadColumns, fileName, auth } = params;
  const lines: string[] = [];

  if (includeConnect) {
    if (includeInstall) lines.push("# pip install amcat4py pandas");
    lines.push("import pandas as pd");
    lines.push("from amcat4py import AmcatClient", "");
    if (auth) {
      lines.push(`# Get your API key at: ${auth.apiKeysUrl}`);
      lines.push(`conn = AmcatClient(${pyString(serverUrl)}, api_key="your_api_key")`);
    } else {
      lines.push(`conn = AmcatClient(${pyString(serverUrl)})`);
    }
    lines.push("");
  }

  const newFields = uploadColumns.filter((c) => c.isNew);
  if (newFields.length > 0) {
    lines.push("# Add all new fields to the project");
    lines.push(`conn.set_fields(`);
    lines.push(`    index=${pyString(projectId)},`);
    lines.push(`    body={`);
    for (const col of newFields) {
      const spec: string[] = [`"type": ${pyString(col.fieldType)}`];
      if (col.identifier) spec.push(`"identifier": True`);
      lines.push(`        ${pyString(col.fieldName)}: {${spec.join(", ")}},`);
    }
    lines.push(`    }`);
    lines.push(`)`);
    lines.push("");
  }

  if (fileExt(fileName) === ".zip") {
    const cols = uploadColumns.length > 0
      ? uploadColumns.map((c) => `${pyString(c.fieldName)}: ...`).join(", ")
      : `"field1": ..., "field2": ...`;
    lines.push(`# We don't provide example code for reading zip-files`);
    lines.push(`# Add code here to read the documents your data source into a list of dicts, e.g.:`);
    lines.push(`# documents = [{${cols}}, ...]`);
    lines.push("");
    lines.push("# Upload the articles to AmCAT");
    lines.push(`conn.upload_documents(index=${pyString(projectId)}, articles=documents)`);
  } else {
    lines.push(`# Read your data file (adjust path and format as needed)`);
    lines.push(`df = ${pyReadFile(fileName)}`);
    lines.push("");

    const renames = uploadColumns.filter((c) => c.csvName !== c.fieldName);
    if (renames.length > 0) {
      lines.push("# Rename columns as needed");

      lines.push(`df = df.rename(columns={`);
      for (const col of renames) {
        lines.push(`    ${pyString(col.csvName)}: ${pyString(col.fieldName)},`);
      }
      lines.push(`})`);
      lines.push("");
    }

    if (uploadColumns.length > 0) {
      lines.push("# Select the appropriate columns");

      lines.push(`df = df[[${uploadColumns.map((c) => pyString(c.fieldName)).join(", ")}]]`);
      lines.push("");
    }

    lines.push("# Upload the articles to AmCAT");
    lines.push(`conn.upload_documents(index=${pyString(projectId)}, articles=df.to_dict(orient="records"))`);
  }
  return lines.join("\n");
}

function generateRUpload(params: UploadParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, uploadColumns, fileName, auth } = params;
  const lines: string[] = [];

  if (includeConnect) {
    if (includeInstall) {
      lines.push(`# install.packages("tidyverse")`);
      lines.push(`# install.packages("amcat4r", repos = c("https://cloud.r-project.org", "https://ccs-amsterdam.r-universe.dev"))`);
    }
    lines.push("library(tidyverse)");
    lines.push("library(amcat4r)", "");
    if (auth) {
      lines.push(`# Get your API key at: ${auth.apiKeysUrl}`);
      lines.push(`amcat_login(${rString(serverUrl)}, api_key = "your_api_key")`);
    } else {
      lines.push(`amcat_login(${rString(serverUrl)})`);
    }
    lines.push("");
  }

  const newFields = uploadColumns.filter((c) => c.isNew);
  if (newFields.length > 0) {
    lines.push("# Add all new fields to the project");
    lines.push(`set_fields(${rString(projectId)}, list(`);
    for (const col of newFields) {
      const spec: string[] = [`type = ${rString(col.fieldType)}`];
      if (col.identifier) spec.push(`identifier = TRUE`);
      lines.push(`  ${col.fieldName} = list(${spec.join(", ")}),`);
    }
    lines.push(`))`);
    lines.push("");
  }

  if (fileExt(fileName) === ".zip") {
    const cols = uploadColumns.length > 0
      ? uploadColumns.map((c) => `${c.fieldName} = ...`).join(", ")
      : `field1 = ..., field2 = ...`;
    lines.push(`# We don't provide example code for reading zip-files`);
    lines.push(`# Add code here to read the documents your data source into a data frame, e.g.:`);
    lines.push(`# df <- tibble(${cols})`);
    lines.push("");
    lines.push("# Upload the articles to AmCAT");
    lines.push(`upload_documents(${rString(projectId)}, df)`);
  } else {
    lines.push(`# Read your data file (adjust path and format as needed)`);
    lines.push(`df <- ${rReadFile(fileName)}`);
    lines.push("");

    if (uploadColumns.length > 0) {
      lines.push("# Select (and rename) columns as needed");
      lines.push(`df <- df |>`);
      lines.push(`  select(`);
      for (const col of uploadColumns) {
        if (col.csvName !== col.fieldName) {
          lines.push(`    ${col.fieldName} = ${col.csvName},`);
        } else {
          lines.push(`    ${col.fieldName},`);
        }
      }
      lines.push(`  )`);
      lines.push("");
    }

    lines.push("# Upload the articles to AmCAT");
    lines.push(`upload_documents(${rString(projectId)}, df)`);
  }
  return lines.join("\n");
}

// --- Update field / tags code generation ---

function pyValue(v: string | number | boolean | null): string {
  if (v === null) return "None";
  if (typeof v === "boolean") return v ? "True" : "False";
  if (typeof v === "number") return String(v);
  return pyString(v);
}

function rValue(v: string | number | boolean | null): string {
  if (v === null) return "NULL";
  if (typeof v === "boolean") return v ? "TRUE" : "FALSE";
  if (typeof v === "number") return String(v);
  return rString(v);
}

function generatePythonUpdateField(params: UpdateFieldParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, field, value, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));
  const idValues = query.filters?.["_id"]?.values;
  const otherFilters = query.filters
    ? Object.fromEntries(Object.entries(query.filters).filter(([k]) => k !== "_id"))
    : {};
  const hasQueries = query.queries && query.queries.length > 0;
  const hasOtherFilters = Object.keys(otherFilters).length > 0;
  const valueStr = value === null ? "YOUR_VALUE" : pyValue(value);
  if (value === null) lines.push(`# Replace YOUR_VALUE with the new value for ${field}`);
  const args: string[] = [
    `    index=${pyString(projectId)}`,
    `    field=${pyString(field)}`,
    `    value=${valueStr}`,
  ];
  if (idValues && idValues.length > 0)
    args.push(`    ids=[${idValues.map((v) => pyString(String(v))).join(", ")}]`);
  if (hasQueries) args.push(`    queries=${pyQueries(query.queries!)}`);
  if (hasOtherFilters) args.push(`    filters=${pyFilters(otherFilters).replace(/\n/g, "\n    ")}`);
  lines.push(`conn.update_by_query(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

function generateRUpdateField(params: UpdateFieldParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, field, value, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));
  const idValues = query.filters?.["_id"]?.values;
  const otherFilters = query.filters
    ? Object.fromEntries(Object.entries(query.filters).filter(([k]) => k !== "_id"))
    : {};
  const hasQueries = query.queries && query.queries.length > 0;
  const hasOtherFilters = Object.keys(otherFilters).length > 0;
  const valueStr = value === null ? "YOUR_VALUE" : rValue(value);
  if (value === null) lines.push(`# Replace YOUR_VALUE with the new value for ${field}`);
  const args: string[] = [
    `  index = ${rString(projectId)}`,
    `  field = ${rString(field)}`,
    `  value = ${valueStr}`,
  ];
  if (idValues && idValues.length > 0)
    args.push(`  ids = c(${idValues.map((v) => rString(String(v))).join(", ")})`);
  if (hasQueries) {
    const queryStr = query.queries!.map((q) => q.query).join(" OR ");
    args.push(`  queries = ${rString(queryStr)}`);
  }
  if (hasOtherFilters) args.push(`  filters = ${rFilters(otherFilters).replace(/\n/g, "\n  ")}`);
  lines.push(`update_by_query(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

function generatePythonUpdateTags(params: UpdateTagsParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, field, tag, action, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));
  const idValues = query.filters?.["_id"]?.values;
  const otherFilters = query.filters
    ? Object.fromEntries(Object.entries(query.filters).filter(([k]) => k !== "_id"))
    : {};
  const hasQueries = query.queries && query.queries.length > 0;
  const hasOtherFilters = Object.keys(otherFilters).length > 0;
  const args: string[] = [
    `    index=${pyString(projectId)}`,
    `    action=${pyString(action)}`,
    `    field=${pyString(field)}`,
    `    tag=${pyString(tag)}`,
  ];
  if (idValues && idValues.length > 0)
    args.push(`    ids=[${idValues.map((v) => pyString(String(v))).join(", ")}]`);
  if (hasQueries) args.push(`    queries=${pyQueries(query.queries!)}`);
  if (hasOtherFilters) args.push(`    filters=${pyFilters(otherFilters).replace(/\n/g, "\n    ")}`);
  lines.push(`conn.tags_update(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

function generateRUpdateTags(params: UpdateTagsParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, query, field, tag, action, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));
  const idValues = query.filters?.["_id"]?.values;
  const otherFilters = query.filters
    ? Object.fromEntries(Object.entries(query.filters).filter(([k]) => k !== "_id"))
    : {};
  const hasQueries = query.queries && query.queries.length > 0;
  const hasOtherFilters = Object.keys(otherFilters).length > 0;
  const args: string[] = [
    `  ${rString(projectId)}`,
    `  ${rString(action)}`,
    `  ${rString(field)}`,
    `  ${rString(tag)}`,
  ];
  if (idValues && idValues.length > 0)
    args.push(`  ids = c(${idValues.map((v) => rString(String(v))).join(", ")})`);
  if (hasQueries) {
    const queryStr = query.queries!.map((q) => q.query).join(" OR ");
    args.push(`  queries = ${rString(queryStr)}`);
  }
  if (hasOtherFilters) args.push(`  filters = ${rFilters(otherFilters).replace(/\n/g, "\n  ")}`);
  lines.push(`update_tags(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

// --- Create project code generation ---

function generatePythonCreateProject(params: CreateProjectParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, name, description, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));
  const id = projectId ? pyString(projectId) : "PROJECT_ID";
  const placeholders: string[] = [];
  if (!projectId) placeholders.push("PROJECT_ID");
  if (placeholders.length) lines.push(`# Replace ${placeholders.join(" and ")} with the desired values`);
  const args: string[] = [`    index=${id}`];
  if (name) args.push(`    name=${pyString(name)}`);
  if (description) args.push(`    description=${pyString(description)}`);
  lines.push(`conn.create_index(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

function generateRCreateProject(params: CreateProjectParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, projectId, name, description, auth } = params;
  const lines: string[] = [];
  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));
  const id = projectId ? rString(projectId) : "PROJECT_ID";
  const placeholders: string[] = [];
  if (!projectId) placeholders.push("PROJECT_ID");
  if (placeholders.length) lines.push(`# Replace ${placeholders.join(" and ")} with the desired values`);
  const args: string[] = [`  ${id}`];
  if (name) args.push(`  name = ${rString(name)}`);
  if (description) args.push(`  description = ${rString(description)}`);
  lines.push(`create_index(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

// --- Reindex code generation ---

function pyFieldOptionsEntry(opts: FieldReindexOptions): string {
  const parts: string[] = [];
  if (opts.rename !== undefined) parts.push(`"rename": ${pyString(opts.rename)}`);
  if (opts.exclude) parts.push(`"exclude": True`);
  if (opts.type !== undefined) parts.push(`"type": ${pyString(opts.type)}`);
  return `{${parts.join(", ")}}`;
}

function pyFieldOptions(fieldOptions: Record<string, FieldReindexOptions>): string {
  const entries = Object.entries(fieldOptions).map(
    ([k, v]) => `        ${pyString(k)}: ${pyFieldOptionsEntry(v)}`,
  );
  return `{\n${entries.join(",\n")}\n    }`;
}

function rFieldOptionsEntry(opts: FieldReindexOptions): string {
  const parts: string[] = [];
  if (opts.rename !== undefined) parts.push(`rename = ${rString(opts.rename)}`);
  if (opts.exclude) parts.push(`exclude = TRUE`);
  if (opts.type !== undefined) parts.push(`type = ${rString(opts.type)}`);
  return `list(${parts.join(", ")})`;
}

function rFieldOptions(fieldOptions: Record<string, FieldReindexOptions>): string {
  const entries = Object.entries(fieldOptions).map(([k, v]) => `    ${k} = ${rFieldOptionsEntry(v)}`);
  return `list(\n${entries.join(",\n")}\n  )`;
}

function generatePythonReindex(params: ReindexParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, sourceProjectId, destProjectId, destProjectName, destMode, query, fieldOptions, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...pyConnect(serverUrl, auth, includeInstall));

  const dest = destProjectId ? pyString(destProjectId) : "DEST_ID";
  if (!destProjectId) lines.push(`# Replace DEST_ID with the destination project id`);

  const hasFields = Object.keys(fieldOptions).length > 0;
  const hasQueries = query.queries && query.queries.length > 0;
  const hasFilters = query.filters && Object.keys(query.filters).length > 0;
  const hasName = destMode === "new" && !!destProjectName;

  const args: string[] = [
    `    index=${pyString(sourceProjectId)}`,
    `    destination=${dest}`,
  ];
  if (hasName) args.push(`    name=${pyString(destProjectName!)}`);
  if (hasFields) args.push(`    fields=${pyFieldOptions(fieldOptions)}`);
  if (hasQueries) args.push(`    queries=${pyQueries(query.queries!)}`);
  if (hasFilters) args.push(`    filters=${pyFilters(query.filters!).replace(/\n/g, "\n    ")}`);

  lines.push(`conn.reindex(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

function generateRReindex(params: ReindexParams, includeInstall: boolean, includeConnect: boolean): string {
  const { serverUrl, sourceProjectId, destProjectId, destProjectName, destMode, query, fieldOptions, auth } = params;
  const lines: string[] = [];

  if (includeConnect) lines.push(...rConnect(serverUrl, auth, includeInstall));

  const dest = destProjectId ? rString(destProjectId) : "DEST_ID";
  if (!destProjectId) lines.push(`# Replace DEST_ID with the destination project id`);

  const hasFields = Object.keys(fieldOptions).length > 0;
  const hasQueries = query.queries && query.queries.length > 0;
  const hasFilters = query.filters && Object.keys(query.filters).length > 0;
  const hasName = destMode === "new" && !!destProjectName;

  const args: string[] = [
    `  index = ${rString(sourceProjectId)}`,
    `  destination = ${dest}`,
  ];
  if (hasName) args.push(`  name = ${rString(destProjectName!)}`);
  if (hasFields) args.push(`  fields = ${rFieldOptions(fieldOptions)}`);
  if (hasQueries) {
    const queryStr = query.queries!.map((q) => q.query).join(" OR ");
    args.push(`  queries = ${rString(queryStr)}`);
  }
  if (hasFilters) args.push(`  filters = ${rFilters(query.filters!).replace(/\n/g, "\n  ")}`);

  lines.push(`reindex(\n${args.join(",\n")}\n)`);
  return lines.join("\n");
}

// --- Aggregate helpers (used by both Python and R generators above) ---

function pyAxis(axis: AggregationOptions["axes"][number]): string {
  const parts = [`"field": ${pyString(axis.field)}`];
  if (axis.interval) parts.push(`"interval": ${pyString(axis.interval)}`);
  return `{${parts.join(", ")}}`;
}

function rAxis(axis: AggregationOptions["axes"][number]): string {
  const parts = [`field = ${rString(axis.field)}`];
  if (axis.interval) parts.push(`interval = ${rString(axis.interval)}`);
  return `list(${parts.join(", ")})`;
}

// --- Public API ---

export function generatePython(action: CodeAction, includeInstall: boolean, includeConnect: boolean): string {
  if (action.action === "search") return generatePythonSearch(action.params, includeInstall, includeConnect);
  if (action.action === "aggregate") return generatePythonAggregate(action.params, includeInstall, includeConnect);
  if (action.action === "fields") return generatePythonFields(action.params, includeInstall, includeConnect);
  if (action.action === "create_field") return generatePythonCreateField(action.params, includeInstall, includeConnect);
  if (action.action === "users") return generatePythonUsers(action.params, includeInstall, includeConnect);
  if (action.action === "add_user") return generatePythonAddUser(action.params, includeInstall, includeConnect);
  if (action.action === "create_project") return generatePythonCreateProject(action.params, includeInstall, includeConnect);
  if (action.action === "upload") return generatePythonUpload(action.params, includeInstall, includeConnect);
  if (action.action === "delete") return generatePythonDelete(action.params, includeInstall, includeConnect);
  if (action.action === "update_field") return generatePythonUpdateField(action.params, includeInstall, includeConnect);
  if (action.action === "update_tags") return generatePythonUpdateTags(action.params, includeInstall, includeConnect);
  if (action.action === "reindex") return generatePythonReindex(action.params, includeInstall, includeConnect);
  return "# Unsupported action";
}

export function generateR(action: CodeAction, includeInstall: boolean, includeConnect: boolean): string {
  if (action.action === "search") return generateRSearch(action.params, includeInstall, includeConnect);
  if (action.action === "aggregate") return generateRAggregate(action.params, includeInstall, includeConnect);
  if (action.action === "fields") return generateRFields(action.params, includeInstall, includeConnect);
  if (action.action === "create_field") return generateRCreateField(action.params, includeInstall, includeConnect);
  if (action.action === "users") return generateRUsers(action.params, includeInstall, includeConnect);
  if (action.action === "add_user") return generateRAddUser(action.params, includeInstall, includeConnect);
  if (action.action === "create_project") return generateRCreateProject(action.params, includeInstall, includeConnect);
  if (action.action === "upload") return generateRUpload(action.params, includeInstall, includeConnect);
  if (action.action === "delete") return generateRDelete(action.params, includeInstall, includeConnect);
  if (action.action === "update_field") return generateRUpdateField(action.params, includeInstall, includeConnect);
  if (action.action === "update_tags") return generateRUpdateTags(action.params, includeInstall, includeConnect);
  if (action.action === "reindex") return generateRReindex(action.params, includeInstall, includeConnect);
  return "# Unsupported action";
}

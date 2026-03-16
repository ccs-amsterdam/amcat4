import { AggregationOptions, AmcatFilter, AmcatFilters, AmcatProjectId, AmcatQuery, AmcatQueryTerm } from "@/interfaces";

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

export type CodeAction =
  | { action: "search"; params: SearchParams }
  | { action: "aggregate"; params: AggregateParams }
  | { action: "fields"; params: FieldsParams }
  | { action: "create_field"; params: CreateFieldParams }
  | { action: "users"; params: UsersParams }
  | { action: "add_user"; params: AddUserParams };

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
  if (includeInstall) lines.push(`# install.packages("amcat4r", repos = "https://ccs-amsterdam.r-universe.dev")`);
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
  return "# Unsupported action";
}

export function generateR(action: CodeAction, includeInstall: boolean, includeConnect: boolean): string {
  if (action.action === "search") return generateRSearch(action.params, includeInstall, includeConnect);
  if (action.action === "aggregate") return generateRAggregate(action.params, includeInstall, includeConnect);
  if (action.action === "fields") return generateRFields(action.params, includeInstall, includeConnect);
  if (action.action === "create_field") return generateRCreateField(action.params, includeInstall, includeConnect);
  if (action.action === "users") return generateRUsers(action.params, includeInstall, includeConnect);
  if (action.action === "add_user") return generateRAddUser(action.params, includeInstall, includeConnect);
  return "# Unsupported action";
}

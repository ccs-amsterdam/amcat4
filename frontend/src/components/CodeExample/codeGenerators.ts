import { AmcatFilter, AmcatFilters, AmcatProjectId, AmcatQuery, AmcatQueryTerm } from "@/interfaces";

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

export type CodeAction = { action: "search"; params: SearchParams };
// Future actions: | { action: "aggregate"; params: AggregateParams }

// --- Python code generation ---

function pyString(s: string): string {
  return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
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

  if (includeConnect) {
    if (includeInstall) {
      lines.push("# pip install amcat4py");
    }
    lines.push("from amcat4py import AmcatClient", "");

    if (auth) {
      lines.push(`# Get your API token at: ${auth.apiKeysUrl}`);
      lines.push(`token = "your_api_token"`, "");
      lines.push(`conn = AmcatClient(${pyString(serverUrl)}, token=token)`);
    } else {
      lines.push(`conn = AmcatClient(${pyString(serverUrl)})`);
    }
    lines.push("");
  }

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

// --- R code generation ---

function rString(s: string): string {
  return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
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

  if (includeConnect) {
    if (includeInstall) {
      lines.push(`# install.packages("amcatr", repos = "https://ccs-amsterdam.r-universe.dev")`);
    }
    lines.push(`library(amcatr)`, "");

    if (auth) {
      lines.push(`# Get your API token at: ${auth.apiKeysUrl}`);
      lines.push(`token <- "your_api_token"`);
      lines.push(`conn <- amcat.connect(${rString(serverUrl)}, token=token)`);
    } else {
      lines.push(`conn <- amcat.connect(${rString(serverUrl)})`);
    }
    lines.push("");
  }

  const hasQueries = query.queries && query.queries.length > 0;
  const hasFilters = query.filters && Object.keys(query.filters).length > 0;
  const hasFields = fields && fields.length > 0;

  const args: string[] = [`  conn`, `  index = ${rString(projectId)}`];
  if (hasQueries) {
    const queryStr = query.queries!.map((q) => q.query).join(" OR ");
    args.push(`  q = ${rString(queryStr)}`);
  }
  if (hasFilters) {
    args.push(`  filters = ${rFilters(query.filters!).replace(/\n/g, "\n  ")}`);
  }
  if (hasFields) {
    args.push(`  fields = c(${fields!.map(rString).join(", ")})`);
  }

  lines.push(`results <- amcat.query(\n${args.join(",\n")}\n)`);

  return lines.join("\n");
}

// --- Public API ---

export function generatePython(action: CodeAction, includeInstall: boolean, includeConnect: boolean): string {
  if (action.action === "search") return generatePythonSearch(action.params, includeInstall, includeConnect);
  return "# Unsupported action";
}

export function generateR(action: CodeAction, includeInstall: boolean, includeConnect: boolean): string {
  if (action.action === "search") return generateRSearch(action.params, includeInstall, includeConnect);
  return "# Unsupported action";
}

import { z } from "zod";

export const amcatConfigSchema = z.object({
  middlecat_url: z.string().url(),
  authorization: z.enum(["allow_guests", "no_auth", "allow_authenticated_guests", "authorized_users_only"]),
  resource: z.string().url(),
  minio: z.boolean().default(false),
});

export const linkArraySchema = z.array(
  z.object({
    label: z.string(),
    href: z.string(),
  }),
);

export const informationLinksSchema = z.array(
  z.object({
    title: z.string(),
    links: linkArraySchema,
  }),
);

export const taskSchema = z.any();

export const amcatBrandingSchema = z.object({
  server_name: z.string().nullish(),
  server_url: z.string().nullish(),
  server_icon: z.string().nullish(),
  welcome_text: z.string().nullish(),
  client_data: z
    .object({
      information_links: informationLinksSchema.nullish(),
      welcome_buttons: linkArraySchema.nullish(),
    })
    .nullish(),
});
export const amcatUserRoles = ["NONE", "METAREADER", "READER", "WRITER", "ADMIN"] as const;
export const amcatUserRoleSchema = z
  .enum(amcatUserRoles)
  .nullish()
  .transform((v) => v ?? "NONE");

export const contactInfoSchema = z.array(
  z.object({
    name: z.string().optional(),
    email: z.string().optional(),
    url: z.string().optional(),
  }),
);

export const amcatIndexSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullish(),
  user_role: amcatUserRoleSchema,
  guest_role: amcatUserRoleSchema.nullish(),
  archived: z.string().nullish(),
  image_url: z.string().nullish(),
  folder: z.string().nullish(),
  contact: contactInfoSchema.nullish(),
  bytes: z.number().nullish(),
});

export const amcatIndexUpdateSchema = amcatIndexSchema
  .partial()
  .required({ id: true })
  .omit({ archived: true })
  .extend({
    archive: z.boolean().optional(),
  });

export const amcatUserDetailsSchema = z.object({
  email: z.string(),
  role: amcatUserRoleSchema,
});

export const amcatFieldTypeSchema = z.enum([
  "text",
  "date",
  "boolean",
  "keyword",
  "number",
  "object",
  "vector",
  "geo",
  "integer",
  "tag",
  "image",
  "video",
  "audio",
  "preprocess",
  "url",
]);
export const amcatElasticFieldTypeSchema = z.enum([
  "text",
  "annotated_text",
  "binary",
  "match_only_text",
  "date",
  "boolean",
  "keyword",
  "constant_keyword",
  "wildcard",
  "integer",
  "byte",
  "short",
  "long",
  "unsigned_long",
  "float",
  "half_float",
  "double",
  "scaled_float",
  "object",
  "flattened",
  "nested",
  "dense_vector",
  "geo_point",
]);
export const amcatSnippetSchema = z.object({
  nomatch_chars: z.number().default(150),
  max_matches: z.number().default(0),
  match_chars: z.number().default(50),
});
export const amcatMetareaderAccessSchema = z.object({
  access: z.enum(["none", "read", "snippet"]),
  max_snippet: amcatSnippetSchema
    .nullish()
    .transform((o) => o || { nomatch_chars: 150, max_matches: 0, match_chars: 50 }),
});
export const amcatClientSettingsSchema = z.object({
  isHeading: z.boolean().nullish(),
  inList: z.boolean().nullish(),
  inDocument: z.boolean().nullish(),
  inListSummary: z.boolean().nullish(),
});
export const amcatFieldSchema = z.object({
  name: z.string(),
  identifier: z.boolean(),
  type: amcatFieldTypeSchema,
  elastic_type: amcatElasticFieldTypeSchema,
  metareader: amcatMetareaderAccessSchema,
  client_settings: amcatClientSettingsSchema,
});

export const amcatFieldValuesSchema = z.array(z.string());

export const amcatFieldStatsSchema = z
  .object({
    count: z.number(),
    min: z.number().nullable(),
    max: z.number().nullable(),
    avg: z.number().nullable(),
    sum: z.number(),
    min_as_string: z.string().nullish(),
    max_as_string: z.string().nullish(),
    sum_as_string: z.string().nullish(),
    avg_as_string: z.string().nullish(),
  })
  .transform((o) => {
    return {
      ...o,
      min_as_string: o.min_as_string ?? String(o.min),
      max_as_string: o.max_as_string ?? String(o.max),
      sum_as_string: o.sum_as_string ?? String(o.sum),
      avg_as_string: o.avg_as_string ?? String(o.avg),
    };
  });

export const amcatArticleSchema = z.record(z.any()).and(
  z.object({
    _id: z.string(),
  }),
);

const amcatQueryResultMetaSchema = z.object({
  total_count: z.number(),
  per_page: z.number(),
  page: z.number(),
  page_count: z.number().nullable(),
});

export const amcatQueryResultSchema = z.object({
  results: z.array(amcatArticleSchema),
  meta: amcatQueryResultMetaSchema,
});

// aggregation
export const amcatAggregationIntervalSchema = z.enum([
  "day",
  "week",
  "month",
  "quarter",
  "year",
  "decade",
  "daypart",
  "dayofweek",
  "monthnr",
  "yearnr",
  "dayofmonth",
  "weeknr",
]);
export const amcatMetricFunctionSchema = z.enum(["sum", "avg", "min", "max"]);
export const amcatAggregateDataPointSchema = z.record(z.union([z.number(), z.string()]));
export const amcatAggregationAxisSchema = z.object({
  field: z.string(),
  name: z.string(),
  interval: amcatAggregationIntervalSchema.nullish().transform((x) => x ?? undefined),
});
export const amcatAggregationMetricSchema = z.object({
  field: z.string(),
  function: amcatMetricFunctionSchema,
  name: z.string().optional(),
  type: z.string().optional(),
});

export const amcatAggregateDataSchema = z.object({
  data: z.array(amcatAggregateDataPointSchema),
  meta: z.object({
    axes: z.array(amcatAggregationAxisSchema),
    aggregations: z.array(amcatAggregationMetricSchema),
    after: z
      .record(z.any())
      .nullish()
      .transform((x) => x ?? undefined),
  }),
});

export const amcatMultimediaListItem = z.object({
  key: z.string(),
  presigned_get: z.optional(z.string()),
  content_type: z.array(z.string().nullish()).nullish(),
  is_dir: z.boolean(),
  last_modified: z.optional(z.coerce.date()),
  size: z.number().nullish(),
});

export const amcatMultimediaPresignedPost = z.object({
  url: z.string(),
  form_data: z.object({
    policy: z.string(),
    "x-amz-algorithm": z.string(),
    "x-amz-credential": z.string(),
    "x-amz-date": z.string(),
    "x-amz-signature": z.string(),
  }),
});

export const amcatMultimediaPresignedGet = z.object({
  url: z.string(),
  content_type: z.array(z.string()),
  size: z.number(),
});

export const amcatPreprocessingInstructionArgumentValue = z.union([
  z.string(),
  z.number(),
  z.boolean(),
  z.array(z.string()),
  z.array(z.number()),
  z.array(z.boolean()),
]);

const amcatPreprocessingInstructionArgument = z.object({
  name: z.string(),
  field: z.string().nullish(),
  value: amcatPreprocessingInstructionArgumentValue.nullish(),
  secret: z.boolean().default(false),
});

export const amcatPreprocessingInstructionOutput = z.object({
  name: z.string(),
  field: z.string(),
});

export const amcatPreprocessingInstruction = z.object({
  field: z.string(),
  task: z.string(),
  endpoint: z.string(),
  arguments: z.array(amcatPreprocessingInstructionArgument),
  outputs: z.array(amcatPreprocessingInstructionOutput),
});

const PreprocessingStatus = z.enum(["Active", "Paused", "Unknown", "Error", "Stopped", "Done"]);

export const amcatPreprocessingInstructionStatus = z.object({
  status: PreprocessingStatus,
});

export const amcatPreprocessingInstructionDetails = z.object({
  instruction: amcatPreprocessingInstruction,
  status: PreprocessingStatus,
  counts: z.object({
    total: z.number(),
    done: z.number().optional(),
    error: z.number().optional(),
  }),
});

const amcatPreprocessingTaskRequest = z.object({
  body: z.enum(["json", "binary"]),
  template: z.any(),
});

const amcatPreprocessingTaskEndpoint = z.object({
  placeholder: z.string(),
  domain: z.array(z.string()),
});

const amcatPreprocessingTaskSetting = z.object({
  name: z.string(),
  type: z.string(),
  path: z.string().nullish(),
});

const amcatPreprocessingTaskOutput = amcatPreprocessingTaskSetting.extend({
  recommended_type: amcatFieldTypeSchema,
});

const amcatPreprocessingTaskParameters = amcatPreprocessingTaskSetting.extend({
  use_field: z.enum(["yes", "no"]),
  default: z.union([z.boolean(), z.string(), z.number()]).nullish(),
  placeholder: z.string().nullish(),
  secret: z.boolean().default(false),
});

export const amcatPreprocessingTask = z.object({
  name: z.string(),
  endpoint: amcatPreprocessingTaskEndpoint,
  parameters: z.array(amcatPreprocessingTaskParameters),
  outputs: z.array(amcatPreprocessingTaskOutput),
  request: amcatPreprocessingTaskRequest,
});

export const amcatRequestProjectRoleSchema = z.object({
  type: z.literal("project_role"),
  project_id: z.string(),
  role: amcatUserRoleSchema,
  message: z.string().nullish(),
});

export const amcatRequestServerRoleSchema = z.object({
  type: z.literal("server_role"),
  role: amcatUserRoleSchema,
  message: z.string().nullish(),
});

export const amcatRequestProjectSchema = z.object({
  type: z.literal("create_project"),
  project_id: z.string(),
  name: z.string().nullish(),
  description: z.string().nullish(),
  folder: z.string().nullish(),
  message: z.string().nullish(),
});

export const amcatRequestSchema = z.object({
  email: z.string(),
  status: z.enum(["pending", "approved", "rejected"]),
  timestamp: z.coerce.date(),
  request: z.discriminatedUnion("type", [
    amcatRequestProjectRoleSchema,
    amcatRequestServerRoleSchema,
    amcatRequestProjectSchema,
  ]),
});

const amcatApiKeyRestrictionsSchema = z.object({
  edit_api_keys: z.boolean().default(false),
  server_role: amcatUserRoleSchema.nullish(),
  default_project_role: amcatUserRoleSchema.nullish(),
  project_roles: z.record(z.string(), z.enum(amcatUserRoles)),
});

export const amcatApiKeySchema = z.object({
  id: z.string(),
  name: z.string(),
  expires_at: z.coerce.date(),
  restrictions: amcatApiKeyRestrictionsSchema,
});

export const amcatApiKeyUpdateResponseSchema = z.object({
  api_key: z.string(),
});

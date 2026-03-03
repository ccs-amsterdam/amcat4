import { z } from "zod";
import {
  amcatAggregateDataPointSchema,
  amcatAggregateDataSchema,
  amcatAggregationAxisSchema,
  amcatAggregationIntervalSchema,
  amcatAggregationMetricSchema,
  amcatArticleSchema,
  amcatBrandingSchema,
  amcatClientSettingsSchema,
  amcatConfigSchema,
  amcatElasticFieldTypeSchema,
  amcatFieldSchema,
  amcatFieldStatsSchema,
  amcatFieldTypeSchema,
  amcatFieldValuesSchema,
  amcatProjectSchema,
  amcatMetareaderAccessSchema,
  amcatMetricFunctionSchema,
  amcatMultimediaListItem,
  amcatMultimediaPresignedPost,
  amcatPreprocessingInstruction,
  amcatPreprocessingTask,
  amcatQueryResultSchema,
  amcatRequestProjectSchema,
  amcatRequestProjectRoleSchema,
  amcatRequestSchema,
  amcatSnippetSchema,
  amcatUserDetailsSchema,
  amcatUserRoleSchema,
  amcatRequestServerRoleSchema,
  amcatApiKeySchema,
} from "./schemas";
import { Axios } from "axios";

export type AmcatConfig = z.infer<typeof amcatConfigSchema>;
export type AmcatBranding = z.infer<typeof amcatBrandingSchema>;
export type AmcatUserRole = z.infer<typeof amcatUserRoleSchema>;
export type AmcatProject = z.infer<typeof amcatProjectSchema>;
export type AmcatUserDetails = z.infer<typeof amcatUserDetailsSchema>;
export type AmcatFieldType = z.infer<typeof amcatFieldTypeSchema>;
export type AmcatElasticFieldType = z.infer<typeof amcatElasticFieldTypeSchema>;
export type AmcatField = z.infer<typeof amcatFieldSchema>;
export type UpdateAmcatField = Partial<AmcatField>;
export type AmcatArticle = z.infer<typeof amcatArticleSchema>;
export type AmcatQueryResult = z.infer<typeof amcatQueryResultSchema>;
export type AmcatFieldValues = z.infer<typeof amcatFieldValuesSchema>;
export type AmcatFieldStats = z.infer<typeof amcatFieldStatsSchema>;
export type AmcatSnippet = z.infer<typeof amcatSnippetSchema>;
export type AmcatMetareaderAccess = z.infer<typeof amcatMetareaderAccessSchema>;
export type AmcatClientSettings = z.infer<typeof amcatClientSettingsSchema>;
export type AggregationInterval = z.infer<typeof amcatAggregationIntervalSchema>;
export type MetricFunction = z.infer<typeof amcatMetricFunctionSchema>;
export type AggregateDataPoint = z.infer<typeof amcatAggregateDataPointSchema>;
export type AggregationAxis = z.infer<typeof amcatAggregationAxisSchema>;
export type AggregationMetric = z.infer<typeof amcatAggregationMetricSchema>;
export type AggregateData = z.infer<typeof amcatAggregateDataSchema>;
export type MultimediaListItem = z.infer<typeof amcatMultimediaListItem>;
export type MultimediaPresignedPost = z.infer<typeof amcatMultimediaPresignedPost>;
export type PreprocessingInstruction = z.infer<typeof amcatPreprocessingInstruction>;
export type PreprocessingTask = z.infer<typeof amcatPreprocessingTask>;
export type DisplayOption = "list" | "table" | "linechart" | "barchart";
export type AmcatRequest = z.infer<typeof amcatRequestSchema>;
export type AmcatRequestProjectRole = z.infer<typeof amcatRequestProjectRoleSchema>;
export type AmcatRequestServerRole = z.infer<typeof amcatRequestServerRoleSchema>;
export type AmcatRequestProject = z.infer<typeof amcatRequestProjectSchema>;
export type AmcatApiKey = z.infer<typeof amcatApiKeySchema>;

export type AmcatProjectId = string;

//TODO: think about how visual and data options relate, e.g. limit.
export interface AggregationOptions {
  /* Aggregation axes, i.e. [{field: "publisher"}] */
  axes: AggregationAxis[];
  /* Display option, i,e, "linechart" or "barchart" */
  display: DisplayOption;
  /* Use a specific metric rather than count -- only allow one metric for now */
  metrics?: AggregationMetric[];
  /* Limit the number of rows/lines/bars */
  limit?: number;
  /* Show a title */
  title?: string;
  /* Pagination */
  after?: Record<string, any>;
}

export interface ChartData {
  rows: AggregateDataPoint[];
  columns: ChartDataColumn[];
  domain: [number, number];
  axes: AggregationAxis[];
  aggregations: AggregationMetric[];
}

export interface ChartDataColumn {
  name: string;
  color: string;
  sum: number;
}

export interface DateFilter {
  lte?: string;
  gte?: string;
  lt?: string;
  gt?: string;
}

export interface AmcatFilter extends DateFilter {
  values?: (string | number)[];
  exists?: boolean;
  justAdded?: boolean;
}

export interface AmcatFilters {
  [field: string]: AmcatFilter;
}

export interface AmcatQueryTerm {
  label?: string;
  query: string;
}

export interface AmcatQuery {
  filters?: AmcatFilters;
  queries?: AmcatQueryTerm[];
}

export interface AmcatQueryFieldSpec {
  name: string;
  snippet?: AmcatSnippet;
}

export interface AmcatQueryParams {
  page?: number;
  fields?: (string | AmcatQueryFieldSpec)[];
  highlight?: boolean;
}

export interface AggregateVisualizerProps {
  /***
   * The data to visualize
   */
  data: ChartData;

  /**
   * Callback when user clicks on a point,
   * should be an array of values of equal length to the # of axes
   * */
  createZoom: (value: (string | number)[]) => void;
  /* Width of the component (default: 100%) */
  width?: string | number;
  /* Height of the component (default: 300) */
  height?: string | number;
  /* Limit the number of bars/lines/rows */
  limit?: number;
}

export type SortSpec = string | string[] | { [field: string]: { order?: "asc" | "desc" } }[];

export interface MenuRoute {
  label: string;
  pathname: string;
  reqRole?: AmcatUserRole;
}

export type UploadOperation = "create" | "update" | "index";

export type MultimediaType = "image" | "video" | "audio";

export type RecentProjects = Record<string, AmcatProject[]>;

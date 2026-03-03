import { AmcatElasticFieldType, MultimediaListItem, UpdateAmcatField, UploadOperation } from "@/interfaces";
import { Column, jsType } from "./Upload";
import { extensionMapping } from "../Multimedia/MultimediaUpload";

export function prepareUploadData(
  data: Record<string, jsType>[],
  columns: Column[],
  operation: UploadOperation,
  multimedia?: MultimediaListItem[],
) {
  const documents = data.map((row) => {
    const newRow: Record<string, jsType> = {};
    for (const column of columns) {
      if (!column.field) continue;
      if (column.status !== "Ready" && column.status !== "Type invalid") continue;
      if (column.field === null) continue;

      if (column.type === "date") setCoercedValueOrSkip(newRow, row[column.name], column.field, coerceDate);
      else if (column.type === "number") setCoercedValueOrSkip(newRow, row[column.name], column.field, coerceNumeric);
      else if (column.type === "boolean") setCoercedValueOrSkip(newRow, row[column.name], column.field, coerceBoolean);
      else newRow[column.field] = row[column.name];
    }

    return newRow;
  });

  const hasNewFields = columns.some((c) => c.field && !c.exists);
  if (!hasNewFields) return { documents, operation };

  const fields: Record<string, UpdateAmcatField> = {};
  columns.forEach((c) => {
    if (c.field && !c.exists && c.type) {
      fields[c.field] = {
        type: c.type,
        identifier: !!c.identifier,
      };
      if (c.elastic_type) fields[c.field].elastic_type = c.elastic_type;
    }
  });
  return { documents: documents, fields, operation };
}

export function autoTypeColumn(data: Record<string, jsType>[], name: string): Column {
  const field = autoNameColumn(name);

  const column: Column = { name, field, type: null, elastic_type: null, status: "Validating", exists: false };

  const isDate = listInvalid(data, name, coerceDate).length / data.length < 0.2;
  if (isDate) return { ...column, type: "date", elastic_type: "date" };

  const isNumber = listInvalid(data, name, coerceNumeric).length / data.length < 0.2;
  if (isNumber) {
    const isInt = listInvalid(data, name, coerceInteger).length === 0;
    if (isInt) return { ...column, type: "integer", elastic_type: "integer" };
    return { ...column, type: "number", elastic_type: "double" };
  }

  const isBoolean = listInvalid(data, name, coerceBoolean).length === 0;
  if (isBoolean) return { ...column, type: "boolean", elastic_type: "boolean" };

  const pctUnique = percentUnique(data, name);
  if (pctUnique < 0.5 && !hasValueLongerThan(data, name, 100))
    return { ...column, type: "keyword", elastic_type: "keyword" };

  return { ...column, type: "text", elastic_type: "text" };
}

export function autoNameColumn(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "_")
    .replace(/^_/, "");
}

function setCoercedValueOrSkip(
  row: Record<string, jsType>,
  value: jsType,
  field: string,
  coercer: (value: jsType) => jsType | null,
) {
  const coerced = coercer(value);
  if (coerced === null) return;
  row[field] = coerced;
}

export async function validateColumns(
  columns: Column[],
  data: Record<string, jsType>[],
  multimedia?: MultimediaListItem[],
): Promise<Column[]> {
  const multimediaDict: Record<string, boolean> = {};
  for (const m of multimedia || []) multimediaDict[m.key] = true;

  return columns.map((column) => {
    if (column.status !== "Validating") return column;

    if (column.type === "keyword") {
      if (hasValueLongerThan(data, column.name, 256)) {
        return {
          ...column,
          status: "Type invalid",
          typeWarning: "Some values are too long (> 256 chars) to be a keyword. These will be skipped",
        };
      }
    }

    if (column.type === "text" || column.type === "keyword") {
      const empty = countEmpty(data, column.name);
      if (empty > 0) {
        return { ...column, status: "Type invalid", typeWarning: `${empty} empty values` };
      }
      const invalid = listInvalid(data, column.name, coerceNumeric);
      if (invalid.length === 0) {
        return {
          ...column,
          status: "Type warning",
          typeWarning: "Contains only numeric values. Are you sure this isn't a 'number' type?",
          invalidExamples: invalid.slice(0, 100),
        };
      }
    }

    if (column.type === "date") {
      const invalidDates = listInvalid(data, column.name, coerceDate);
      if (invalidDates.length > 0) {
        return {
          ...column,
          status: "Type invalid",
          typeWarning: `${invalidDates.length} invalid dates`,
          invalidExamples: invalidDates.slice(0, 100),
        };
      }
    }

    if (column.type === "number") {
      if (signedIntegerType(column.elastic_type)) {
        const invalidIntegers = listInvalid(data, column.name, coerceInteger);
        if (invalidIntegers.length > 0) {
          return {
            ...column,
            status: "Type invalid",
            typeWarning: `${invalidIntegers.length} invalid integers`,
            invalidExamples: invalidIntegers.slice(0, 100),
          };
        }
      } else if (unsignedIntegerType(column.elastic_type)) {
        const invalidIntegers = listInvalid(data, column.name, coerceUnsignedInteger);
        if (invalidIntegers.length > 0) {
          return {
            ...column,
            status: "Type invalid",
            typeWarning: `${invalidIntegers.length} invalid unsigned integers`,
            invalidExamples: invalidIntegers.slice(0, 100),
          };
        }
      } else {
        const invalidDoubles = listInvalid(data, column.name, coerceNumeric);
        if (invalidDoubles.length > 0) {
          return {
            ...column,
            status: "Type invalid",
            typeWarning: `${invalidDoubles.length} invalid numbers`,
            invalidExamples: invalidDoubles.slice(0, 100),
          };
        }
      }
    }

    if (column.type === "boolean") {
      const invalidBooleans = listInvalid(data, column.name, coerceBoolean);
      if (invalidBooleans.length > 0) {
        return {
          ...column,
          status: "Type invalid",
          typeWarning: `${invalidBooleans.length} invalid booleans`,
          invalidExamples: invalidBooleans,
        };
      }
    }

    if (column.type === "image") {
      const invalidImages = invalidMultimedia(data, column.name, "image", multimediaDict);
      if (invalidImages.length > 0) {
        return {
          ...column,
          status: "Type invalid",
          typeWarning: `${invalidImages.length} links to missing images`,
          invalidExamples: invalidImages.slice(0, 5),
        };
      }
    }

    if (column.type === "video") {
      const invalidVideos = invalidMultimedia(data, column.name, "video", multimediaDict);
      if (invalidVideos.length > 0) {
        return {
          ...column,
          status: "Type invalid",
          typeWarning: `${invalidVideos.length} links to missing videos`,
          invalidExamples: invalidVideos.slice(0, 100),
        };
      }
    }

    return { ...column, status: "Ready" };
  });
}

function coerceNumeric(value: jsType) {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    // if a number doesn't start with a number > 0, it's not a number
    if (/^[1-9]/.test(value)) {
      const num = Number(value);
      if (!isNaN(num)) return num;
    }
  }
  return null;
}

function coerceInteger(value: jsType) {
  const num = coerceNumeric(value);
  if (num === null) return null;
  if (Number.isInteger(num)) return num;
  return null;
}

function coerceUnsignedInteger(value: jsType) {
  const num = coerceInteger(value);
  if (num === null) return null;
  if (num < 0) return null;
  return num;
}

function coerceDate(value: jsType) {
  if (typeof value !== "string" || !value.includes("-")) return null;

  if (!value.includes("Z")) value += "Z";
  const date = new Date(value);
  if (isNaN(date.getTime())) return null;

  if (value.includes(":")) return date.toISOString();
  return date.toISOString().split("T")[0];
}

function coerceBoolean(value: jsType) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (value.toLowerCase() === "true") return true;
    if (value.toLowerCase() === "false") return false;
  }
  if (typeof value === "number") {
    if (value === 0) return false;
    if (value === 1) return true;
  }
  return null;
}

function signedIntegerType(elastic_type: AmcatElasticFieldType | null) {
  return elastic_type && ["long", "integer", "short", "byte"].includes(elastic_type);
}
function unsignedIntegerType(elastic_type: AmcatElasticFieldType | null) {
  return elastic_type && ["unsigned_long"].includes(elastic_type);
}

function listInvalid(data: Record<string, jsType>[], column: string, validator: (value: jsType) => jsType | null) {
  return data.filter((d) => validator(d[column]) === null).map((d) => String(d[column]));
}

function invalidMultimedia(
  data: Record<string, jsType>[],
  column: string,
  type: "image" | "video",
  multimediaDict: Record<string, boolean>,
) {
  return data
    .filter((d) => {
      const value = String(d[column]);

      // we cannot validate external links (or maybe we can, but not now)
      if (/^https?:\/\//.test(value)) return false;

      // check if the extension is valid
      const ext = value.split(".").pop()?.toLowerCase();
      if (!ext) return true;
      const mime = extensionMapping[ext];
      if (!mime || !mime.includes(type)) return true;

      // check if the multimedia exists
      if (!multimediaDict[value]) return true;
      return false;
    })
    .map((d) => String(d[column]));
}

function countEmpty(data: Record<string, jsType>[], column: string) {
  return data.filter((d) => d[column] === "").length;
}

function percentUnique(data: Record<string, jsType>[], column: string) {
  const unique = new Set(data.map((d) => d[column])).size;
  return unique / data.length;
}

function hasValueLongerThan(data: Record<string, jsType>[], column: string, max: number) {
  return data.some((d) => String(d[column]).length > max);
}

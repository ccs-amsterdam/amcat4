import { Fragment, type JSX } from "react";
import { Control, ControllerRenderProps, FieldValues, Path } from "react-hook-form";
import { z } from "zod";
import { FormControl, FormField, FormItem, FormLabel } from "./form";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./table";
import { Input } from "./input";
import { X } from "lucide-react";

// Generic form for arrays of objects (with string values).
// Also allows one (and only one) key to have a nested array of objects.
// type TYPE = Record<string, string | Record<string, string>[]>[];

type ValidZod = z.ZodArray<z.ZodObject<any>>;

interface FormFieldProps<T extends FieldValues, Z extends ValidZod> {
  control: Control<T, any>;
  name: Path<T>;
  label: string;
  schema: Z;
}

export function JSONForm<T extends FieldValues, Z extends ValidZod>({
  control,
  name,
  label,
  schema,
}: FormFieldProps<T, Z>) {
  const tableHeadStyle = "h-8 px-3 py-1 text-foreground text-base font-thin ";

  return (
    <FormField
      control={control}
      key={name}
      name={name}
      render={({ field }) => {
        const rows = field.value ? field.value : ([] as z.infer<Z>);
        const rowProjects = rows.map((_, i: number) => i);
        rowProjects.push(rowProjects.length);

        return (
          <FormItem className="flex flex-col">
            <FormLabel>{label}</FormLabel>
            <FormControl>
              <Table className="w-full flex-auto table-fixed">
                <TableHeader className="border-">
                  <TableRow className="border-none p-0 hover:bg-transparent">
                    {flatHeaders(schema).map((key) => (
                      <TableHead key={key} className={`${tableHeadStyle} pl-0`}>
                        {key}
                      </TableHead>
                    ))}
                    <TableHead className={`${tableHeadStyle} w-4 `}></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="">
                  {rowProjects.map((row_i: number) => (
                    <Fragment key={row_i}>
                      {flatForms(schema, field, rows, row_i).map((subRow, subrow_i, arr) => {
                        const lastRow = rows.length <= row_i;
                        const lastSubRow = arr.length > 1 && arr.length - 1 === subrow_i;

                        return (
                          <TableRow
                            key={row_i + "." + subrow_i}
                            className={`${lastRow || lastSubRow ? "opacity-50" : ""} border-none hover:bg-transparent `}
                          >
                            {subRow.map((form, form_i) => (
                              <TableCell
                                key={"cell." + row_i + "." + subrow_i + "." + form_i}
                                className={`${lastSubRow ? "pb-3" : "pb-1"} rounded-none border-none px-0 pl-0 pr-1 pt-0 hover:bg-transparent`}
                              >
                                {form}
                              </TableCell>
                            ))}
                            <TableCell key={"add"} className={` rounded-none px-1 py-1 hover:bg-transparent`}>
                              <X
                                className={`h-5 w-5 select-none text-foreground/50 ${lastRow || lastSubRow ? "text-foreground/20" : "cursor-pointer text-foreground/50 hover:text-destructive"}`}
                                onClick={() => {
                                  if (lastRow || lastSubRow) return;
                                  const values = rmRow(rows, row_i, subrow_i);
                                  field.onChange(values);
                                }}
                              />
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </Fragment>
                  ))}
                </TableBody>
              </Table>
            </FormControl>
          </FormItem>
        );
      }}
    />
  );
}

function addRow<Z extends ValidZod>(schema: Z, values: z.infer<Z>) {
  const newValues = [...values];
  const row: Partial<z.infer<Z>> = {};

  for (let [key, value] of Object.entries(schema.element.shape)) {
    if (isZodString(value)) {
      row[key as keyof z.infer<Z>] = "" as any;
    }
    if (isZodArray(value)) {
      row[key as keyof z.infer<Z>] = [] as any;
    }
  }
  newValues.push(row as z.infer<Z>);
  return newValues;
}

function addSubRow<Z extends ValidZod>(schema: Z, values: z.infer<Z>, i: number) {
  const newValues = [...values];
  for (let [key, value] of Object.entries(schema.element.shape)) {
    if (!isZodArray(value)) continue;
    const keys = Object.keys(value.element.shape);
    const subrow: Z = keys.reduce((acc: any, key) => {
      acc[key] = "";
      return acc;
    }, {});
    const addToRow = newValues[i][key as keyof z.infer<Z>] as z.infer<Z>;
    addToRow.push(subrow);
  }
  return newValues;
}

function rmRow<Z extends ValidZod>(values: z.infer<Z>, row: number, subrow: number) {
  const newValues = [...values];
  if (subrow === 0) {
    newValues.splice(row, 1);
  } else {
    for (let [, value] of Object.entries(newValues[row])) {
      if (Array.isArray(value)) {
        value.splice(subrow, 1);
      }
    }
  }
  return newValues;
}

function flatHeaders(schema: ValidZod) {
  const headers: string[] = [];
  for (let [key, value] of Object.entries(schema.element.shape)) {
    if (isZodString(value)) headers.push(key);
  }
  for (let [, value] of Object.entries(schema.element.shape)) {
    if (isZodArray(value)) headers.push(...Object.keys(value.element.shape));
  }

  return headers;
}

function flatForms<T extends FieldValues, Z extends ValidZod>(
  schema: Z,
  field: ControllerRenderProps<T>,
  rows: z.infer<Z>,
  i: number,
) {
  const formRows: JSX.Element[][] = [[]];
  let newRows: any = [...rows];

  const formStyle = "rounded-none border-none bg-gray-200 dark:bg-gray-600 focus-visible:ring-0";

  for (let [key, value] of Object.entries(schema.element.shape)) {
    if (!isZodString(value)) continue;
    formRows[0].push(
      <Input
        key={key}
        className={formStyle}
        value={String(newRows[i]?.[key] || "")}
        onChange={(v) => {
          if (newRows.length <= i) newRows = addRow(schema, newRows);
          newRows[i][key as keyof z.infer<Z>] = v.target.value as any;
          field.onChange(newRows);
        }}
      />,
    );
  }

  const fixedFields = formRows[0].length;

  for (let [key, value] of Object.entries(schema.element.shape)) {
    if (!isZodArray(value)) continue;
    const nestedKeys = Object.keys(value.element.shape);
    let nestedRows = newRows[i] ? newRows[i][key].length : 0;

    for (let j = 0; j < nestedRows + 1; j++) {
      if (j > 0) {
        formRows.push([]);
        for (let empty = 0; empty < fixedFields; empty++) {
          formRows[j].push(<div key={"empty" + empty} />);
        }
      }

      formRows[j].push(
        ...nestedKeys.map((nestedKey) => (
          <Input
            key={nestedKey}
            className={formStyle}
            value={String(newRows[i]?.[key]?.[j]?.[nestedKey] || "")}
            onChange={(v) => {
              if (newRows.length <= i) newRows = addRow(schema, newRows);
              if (newRows[i][key].length <= j) newRows = addSubRow(schema, newRows, i);
              newRows[i][key][j][nestedKey] = v.target.value;
              field.onChange(newRows);
            }}
          />
        )),
      );
    }
  }

  return formRows;
}

function isZodString(value: any): value is z.ZodString {
  return (
    value instanceof z.ZodString || (value instanceof z.ZodOptional && value._def.innerType instanceof z.ZodString)
  );
}

function isZodArray(value: any): value is z.ZodArray<any> {
  return value instanceof z.ZodArray || (value instanceof z.ZodOptional && value._def.innerType instanceof z.ZodArray);
}

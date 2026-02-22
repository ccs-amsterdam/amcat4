import { DataTable, tooltipHeader } from "@/components/ui/datatable";
import { AmcatClientSettings, AmcatField, AmcatMetareaderAccess, UpdateAmcatField } from "@/interfaces";
import { ColumnDef } from "@tanstack/react-table";
import { Key, ListPlus, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DynamicIcon } from "../ui/dynamic-icon";
import { Input } from "../ui/input";
import MetareaderAccessForm from "./MetareaderAccessForm";
import VisibilityForm from "./VisibilityForm";

import { Button } from "../ui/button";
import CreateField from "./CreateField";

interface Row extends AmcatField {
  onChange?: ({ name, type, metareader, client_settings }: UpdateAmcatField) => void;
}

const tableColumns: ColumnDef<Row>[] = [
  {
    accessorKey: "identifier",
    header: "ID",
    cell: ({ row }) => {
      return row.original.identifier ? <Key className="h-5 w-5 " /> : null;
    },
    size: 10,
  },
  {
    accessorKey: "name",
    header: "Field",
  },
  {
    accessorKey: "type",
    header: "Type",

    cell: ({ row }) => {
      return (
        <div className="flex items-center gap-2">
          <DynamicIcon type={row.original.type} />
          <div>
            <div>{row.original.type}</div>
            <div className="text-xs  leading-3 text-primary">{row.original.elastic_type}</div>
          </div>
        </div>
      );
    },
  },

  {
    id: "Display",
    header: tooltipHeader(
      "Dashboard",
      "Set how this field is displayed in the dashboard. This does not (!!) affect data access (see METAREADER access).",
    ),
    cell: ({ row }) => {
      const field = row.original;

      function onChange(client_settings: AmcatClientSettings) {
        field.onChange?.({ name: field.name, client_settings });
      }

      return <VisibilityForm field={field} client_settings={field.client_settings} onChange={onChange} />;
    },
  },
  {
    header: "METAREADER access",
    cell: ({ row }) => {
      const field = row.original;
      const metareader_access = field.metareader;

      function onChange(metareader: AmcatMetareaderAccess) {
        field.onChange?.({ name: field.name, metareader });
      }
      function changeAccess(access: "none" | "snippet" | "read") {
        onChange({ ...metareader_access, access });
      }
      function changeMaxSnippet(nomatch_chars: number, max_matches: number, match_chars: number) {
        onChange({ ...metareader_access, max_snippet: { nomatch_chars, max_matches, match_chars } });
      }

      return (
        <MetareaderAccessForm
          field={field}
          metareader_access={metareader_access}
          onChangeAccess={changeAccess}
          onChangeMaxSnippet={changeMaxSnippet}
        />
      );
    },
  },
];

interface Props {
  fields: AmcatField[];
  mutate: (action: "create" | "delete" | "update", fields: UpdateAmcatField[]) => void;
}

export default function FieldTable({ fields, mutate }: Props) {
  const [globalFilter, setGlobalFilter] = useState("");
  const [debouncedGlobalFilter, setDebouncedGlobalFilter] = useState(globalFilter);

  useEffect(() => {
    const timeout = setTimeout(() => {
      setGlobalFilter(debouncedGlobalFilter);
    }, 250);
    return () => clearTimeout(timeout);
  }, [debouncedGlobalFilter]);

  const onChange = useCallback(
    (newField: UpdateAmcatField) => {
      mutate("update", [newField]);
    },
    [fields],
  );

  const onCreate = useCallback(
    (newField: UpdateAmcatField) => {
      mutate("create", [newField]);
    },
    [fields],
  );
  const data: Row[] =
    fields?.map((field) => {
      const row: Row = {
        ...field,
        onChange,
      };
      return row;
    }) || [];

  return (
    <div>
      <div className="flex items-center justify-between pb-4">
        <div className="prose-xl flex gap-1 md:gap-3">
          <h3 className="">Fields</h3>
          <CreateField fields={fields} onCreate={onCreate}>
            <Button variant="ghost" className="flex gap-2 p-4">
              <ListPlus />
              <span className="hidden sm:inline">Add field</span>
            </Button>
          </CreateField>
        </div>
        <div className="relative ml-auto flex items-center">
          <Input
            className="max-w-1/2 w-40 pl-8"
            value={debouncedGlobalFilter}
            onChange={(e) => setDebouncedGlobalFilter(e.target.value)}
          />
          <Search className="absolute left-2  h-5 w-5" />
        </div>
      </div>
      <DataTable columns={tableColumns} data={data} globalFilter={globalFilter} pageSize={50} />
    </div>
  );
}

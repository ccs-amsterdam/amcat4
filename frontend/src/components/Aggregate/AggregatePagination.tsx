import { ChartData, ChartDataColumn } from "@/interfaces";
import { DropdownMenuGroup } from "@radix-ui/react-dropdown-menu";
import { ArrowLeft, ArrowRight, ChevronDown } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";

interface Pagination {
  page: number;
  pageSize: number;
  n: number;
  columns: ChartDataColumn[];
  allColumns: ChartDataColumn[];
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
  setColumns: (columns: ChartDataColumn[]) => void;
}

export function useAggregatePagination(data?: ChartData, defaultPageSize: number = 50, defaultNColumns: number = 10) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [columns, setColumns] = useState<ChartDataColumn[] | undefined>();

  useEffect(() => {
    setPage(0);
  }, [data, pageSize]);

  useEffect(() => {
    const [columns, axes] = [data?.columns, data?.axes];
    if (!columns || !axes || axes.length !== 2 || columns.length < defaultNColumns) {
      setColumns(undefined);
      return;
    }
    const sortedColumns = columns.sort((a, b) => b.sum - a.sum);
    setColumns(sortedColumns.slice(0, defaultNColumns));
  }, [data?.axes, data?.columns, defaultNColumns]);

  const paginatedData: ChartData | undefined = useMemo(() => {
    if (!data) return data;

    const start = page === 0 ? 0 : page * pageSize;
    const end = start + pageSize;
    let rows = data.rows.slice(start, end);

    return { ...data, rows, columns: columns || data.columns };
  }, [page, data, pageSize, columns]);

  return {
    paginatedData,
    pagination: {
      page,
      n: data?.rows.length || 0,
      pageSize,
      columns: columns || data?.columns || [],
      allColumns: data?.columns || [],
      setPage,
      setPageSize,
      setColumns,
    },
  };
}

interface Props {
  data: ChartData;
  pagination: Pagination;
}

const pageSizeOptions = [
  { label: "10", value: 10 },
  { label: "25", value: 25 },
  { label: "50", value: 50 },
  { label: "100", value: 100 },
  { label: "250", value: 250 },
  { label: "500", value: 500 },
  { label: "1000", value: 1000 },
  { label: "All", value: Infinity },
];

export default function AggregatePagination({ data, pagination }: Props) {
  const hasPagination = data.rows.length < pagination.n;
  const showPageSize = pagination.n > pageSizeOptions[0].value;
  const hasColumnSelection = pagination.allColumns.length > 1;
  const nPages = Math.ceil(pagination.n / pagination.pageSize);

  function onToggleColumn(event: any, column: ChartDataColumn) {
    event.preventDefault();
    const columnI = pagination.columns?.findIndex((c) => c.name === column.name);
    if (columnI === -1) {
      pagination.setColumns([...(pagination.columns || []), column]);
    } else {
      pagination.setColumns(pagination.columns?.filter((c) => c.name !== column.name));
    }
  }

  const remainingColumns = useMemo(() => {
    if (!pagination.columns) return [];
    return pagination.allColumns.filter((c) => !pagination.columns?.find((pc) => pc.name === c.name));
  }, [pagination]);

  return (
    <div className="flex h-10 justify-end gap-3 text-sm text-foreground">
      <DropdownMenu>
        <DropdownMenuTrigger
          className={`flex items-center gap-1 px-1 text-sm ${hasColumnSelection ? "block" : "hidden"}`}
        >
          {pagination?.columns?.length} columns <ChevronDown className="h-4 w-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuGroup className="max-h-72 overflow-auto">
            {pagination.columns.map((column) => {
              return (
                <DropdownMenuItem key={column.name} onClick={(e) => onToggleColumn(e, column)}>
                  <div className="mr-2 h-4 w-2 rounded-full" style={{ background: column.color }}></div>
                  {column.name}
                </DropdownMenuItem>
              );
            })}
            {remainingColumns.map((column) => {
              return (
                <DropdownMenuItem key={column.name} onClick={(e) => onToggleColumn(e, column)}>
                  <div className="mr-2 h-4 w-2 rounded-full"></div>
                  {column.name}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <DropdownMenu>
        <DropdownMenuTrigger className={`flex items-center gap-1 px-1 text-sm ${showPageSize ? "block" : "hidden"}`}>
          {hasPagination ? `${pagination.pageSize}` : "show all"} <ChevronDown className="h-4 w-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>Show per page</DropdownMenuLabel>
          {pageSizeOptions.map((option) => {
            if (option.value > pagination.n && pagination.n !== 0 && option.label !== `All`) return null;
            return (
              <DropdownMenuItem key={option.value} onClick={() => pagination.setPageSize(option.value)}>
                {option.label === "All" ? `${pagination.n} (all)` : option.label}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
      <div className={`grid select-none grid-cols-[auto,1fr,auto] items-center ${hasPagination ? "block" : "hidden"}`}>
        <Button
          variant="ghost"
          className="flex gap-3 px-1"
          onClick={() => pagination.setPage(pagination.page - 1)}
          disabled={pagination.page === 0}
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="grid grid-cols-[1fr,auto,1fr]">
          <div className="text-center">{pagination.page + 1} </div>
          <div className="px-1">of</div>
          <div> {nPages}</div>
        </div>
        <Button
          variant="ghost"
          className="flex gap-3 px-1"
          onClick={() => pagination.setPage(pagination.page + 1)}
          disabled={data.rows.length < pagination.pageSize}
        >
          <ArrowRight className="h-5 w-5" />
        </Button>
      </div>
    </div>
  );
}

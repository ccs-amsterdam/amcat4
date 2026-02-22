"use client";

import {
  ColumnDef,
  SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "./button";
import { StepBack, StepForward } from "lucide-react";
import { useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./tooltip";

interface DataTableProps<TData extends Record<string, any>, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  globalFilter?: string;
  pagination?: {
    pageCount: number;
    pageIndex: number;
    nextPage: () => void;
    prevPage: () => void;
  };
  loading?: boolean;
  pageSize?: number;
  sortable?: boolean; // !!! only works if all data is known (so pagination not manual)
}

export function DataTable<TData extends Record<string, any>, TValue>({
  columns,
  data,
  globalFilter,
  pagination,
  pageSize = 6,
}: DataTableProps<TData, TValue>) {
  const manualPagination = !!pagination;
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    pageCount: manualPagination ? pagination.pageCount : undefined,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    onSortingChange: setSorting,
    getSortedRowModel: getSortedRowModel(),
    state: manualPagination
      ? { globalFilter, pagination: { pageIndex: pagination.pageIndex, pageSize } }
      : { globalFilter, sorting },
    initialState: {
      pagination: {
        pageIndex: 0,
        pageSize,
      },
    },
  });

  const canPaginate = table.getCanNextPage() || table.getCanPreviousPage();

  return (
    <div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  return (
                    <TableHead key={header.id} style={{ width: `${header.getSize()}px` }}>
                      {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} data-state={row.getIsSelected() && "selected"}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  No results.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className={`${canPaginate ? "flex" : "hidden"} select-none items-center justify-end space-x-2 py-4`}>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => (manualPagination ? pagination.prevPage() : table.previousPage())}
          disabled={!table.getCanPreviousPage()}
        >
          <StepBack />
        </Button>
        <div className="grid grid-cols-[1fr,auto,1fr] gap-2">
          <div>{table.getState()?.pagination?.pageIndex + 1}</div>
          <div>of</div>
          <div>{table.getPageCount()}</div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => (manualPagination ? pagination.nextPage() : table.nextPage())}
          disabled={!table.getCanNextPage()}
        >
          <StepForward />
        </Button>
      </div>
    </div>
  );
}

export function tooltipHeader(name: string, tooltip: string) {
  return () => {
    return (
      <Tooltip>
        <TooltipTrigger>{name}</TooltipTrigger>
        <TooltipContent sideOffset={20} className="max-w-80">
          {tooltip}
        </TooltipContent>
      </Tooltip>
    );
  };
}

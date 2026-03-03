import * as React from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuPortal,
  DropdownMenuTrigger,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { Delete } from "lucide-react";

import type { JSX } from "react";

interface Props {
  placeholder: string;
  options: Option[];
  value: string | undefined;
  value2?: string | undefined;
  onChange: ({}: { value?: string | undefined; value2?: string }) => void;
  clearable?: boolean;
  label?: string;
  disabled?: boolean;
}

export interface Option {
  text: string;
  value: string;
  icon?: JSX.Element;
  options?: Option2[];
  [any: string | number]: any;
}

export interface Option2 {
  text: string;
  value: string;
  icon?: JSX.Element;
  [any: string | number]: any;
}

export function Dropdown({ placeholder, options, value, value2, onChange, clearable, label, disabled = false }: Props) {
  const selected = options.find((o) => o.value === value);
  const selected2 = value2 ? selected?.options?.find((o) => o.value === value2) : undefined;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        className="flex w-full min-w-[10rem] items-center gap-2 rounded-md bg-background px-2 py-1"
      >
        {selected ? (
          <>
            {selected.icon}
            <div>{selected.text}</div>
            <div>{selected2 ? `(${selected2.text})` : null}</div>
          </>
        ) : (
          placeholder
        )}
      </DropdownMenuTrigger>

      <DropdownMenuContent className="max-h-screen overflow-auto">
        {label ? <DropdownMenuLabel>{label}</DropdownMenuLabel> : null}
        {clearable && selected ? (
          <DropdownMenuItem key="_CLEAR_VALUE" onClick={() => onChange({})} className="text-destructive">
            <div className="flex items-center gap-2">
              <Delete />
              Clear
            </div>
          </DropdownMenuItem>
        ) : null}
        {options.map((option) => {
          if (option.options)
            return (
              <DropdownMenuSub key={option.value}>
                <DropdownMenuSubTrigger className="flex items-center gap-2">
                  {option.icon || null}
                  {option.text}
                </DropdownMenuSubTrigger>
                <DropdownMenuPortal>
                  <DropdownMenuSubContent className="max-h-screen overflow-auto">
                    {option.options.map((option2) => {
                      return (
                        <DropdownMenuItem
                          key={option2.value}
                          onClick={() =>
                            onChange({
                              value: option.value,
                              value2: option2.value,
                            })
                          }
                        >
                          <div className="flex items-center gap-2">
                            {option2.icon || null}
                            {option2.text}
                          </div>
                        </DropdownMenuItem>
                      );
                    })}
                  </DropdownMenuSubContent>
                </DropdownMenuPortal>
              </DropdownMenuSub>
            );
          return (
            <DropdownMenuItem key={option.value} onClick={() => onChange({ value: option.value })}>
              <div className="flex items-center gap-2">
                {option.icon || null}
                {option.text}
              </div>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

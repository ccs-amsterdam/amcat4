import * as React from "react";
import { Calendar } from "@/components/ui/calendar";

interface Props {
  label: string;
  value: Date | undefined;
  min: Date | undefined;
  max: Date | undefined;
  onChange: (value: Date | undefined) => void;
}

export default function DatePicker({ label, value, min, max, onChange }: Props) {
  const hidden: any = [];
  if (min) {
    hidden.push({
      before: min,
    });
  }
  if (max) {
    hidden.push({
      after: max,
    });
  }

  return (
    <div className="flex flex-col">
      <h3 className="rounded-t bg-primary p-1 text-center font-bold text-primary-foreground">{label.toUpperCase()}</h3>
      <Calendar
        mode="single"
        selected={value}
        onSelect={onChange}
        captionLayout="dropdown-months"
        className="border border-primary p-1"
        startMonth={min}
        endMonth={max}
        hidden={hidden}
        // initialFocus
      />
    </div>
  );
}

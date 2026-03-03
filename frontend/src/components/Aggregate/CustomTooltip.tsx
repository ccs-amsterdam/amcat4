import { ArrowRight } from "lucide-react";
import React, { useEffect } from "react";

import { TooltipProps } from "recharts";
import { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";

type tProps = TooltipProps<ValueType, NameType>;
interface Props extends tProps {
  value: string;
  onChangeGroup?: (name: string) => void;
}

export const CustomTooltip = ({
  active,
  payload,
  label,
  value,
  coordinate,
  viewBox,
  onChangeGroup,
  ...props
}: Props) => {
  function returnGroup() {
    if (!onChangeGroup || !coordinate?.y || !viewBox?.y || !viewBox.height || !payload) return 0;
    const yValue = (coordinate?.y - viewBox.y) / viewBox.height;
    const bins = 1 / payload.length;
    const payloadI = Math.min(Math.floor(yValue / bins), payload.length - 1);
    const group = String(payload[payloadI]?.name) || "";
    onChangeGroup(group);
  }
  useEffect(() => {
    returnGroup();
  });

  if (active && payload && payload.length) {
    const sorted = payload.sort((p1, p2) => (Number(p2?.value) || 0) - (Number(p1?.value) || 0));
    let firstItem = 0;
    if (value) {
      const index = sorted.findIndex((p) => p.name === value);
      if (index > 0) firstItem = Math.max(0, index - 2);
    }
    if (firstItem + 5 > sorted.length) firstItem = Math.max(0, sorted.length - 5);

    const items = sorted.slice(firstItem, firstItem + 5).map((p) => ({ name: p.name, value: p.value, color: p.color }));
    const others = sorted.length - items.length;
    return (
      <div className="rounded-md border-[1px] border-gray-400 bg-background/70 p-3">
        <h3 className="mb-2 text-sm font-semibold">{label}</h3>
        <div className="grid grid-cols-[25px,auto,1fr,1fr] items-center ">
          {items.map((item, i) => {
            return (
              <React.Fragment key={item.name}>
                <div>{item.name === value ? <ArrowRight className="h-5 w-5" /> : null}</div>
                <div
                  className="h-3 w-3 rounded-full border-[1px] border-black "
                  style={{ background: item.color }}
                ></div>
                <span className="pl-2 pr-5 font-semibold">{item.name}</span>
                <span>{item.value}</span>
              </React.Fragment>
            );
          })}
        </div>
        {others > 0 ? <div className="mt-1  italic">({others} others)</div> : null}
      </div>
    );
  }
};

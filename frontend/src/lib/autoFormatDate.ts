import { AggregationInterval } from "@/interfaces";

export function autoFormatDate(minTime: number, maxTime: number, minValues: number): AggregationInterval {
  let autoFormat: AggregationInterval = "day";
  if (maxTime - minTime > 1000 * 60 * 60 * 24 * minValues) autoFormat = "day";
  if (maxTime - minTime > 1000 * 60 * 60 * 24 * 30 * minValues) autoFormat = "month";
  if (maxTime - minTime > 1000 * 60 * 60 * 24 * 30 * 3 * minValues) autoFormat = "quarter";
  if (maxTime - minTime > 1000 * 60 * 60 * 24 * 365 * minValues) autoFormat = "year";
  if (maxTime - minTime > 1000 * 60 * 60 * 24 * 365 * 10 * minValues) autoFormat = "decade";

  return autoFormat;
}

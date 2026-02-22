import { AggregateData } from "@/interfaces";
import { createChartData } from "./createChartData";

interface Input {
  data: AggregateData;
  sorted: boolean;
}

self.onmessage = (e: MessageEvent<Input>) => {
  try {
    const chartData = createChartData(e.data.data, e.data.sorted);
    self.postMessage({ status: "success", chartData });
  } catch (e) {
    self.postMessage({ status: "error", chartData: undefined });
  }
};

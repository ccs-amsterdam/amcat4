import { AggregateData, ChartData } from "@/interfaces";
import { useEffect, useRef, useState } from "react";

type Status = "loading" | "success" | "error";

import MyWorker from "./createChartDataWorker.ts?worker";

export default function useCreateChartData(data: AggregateData | null, sorted: boolean = false): ChartData | undefined {
  const [chartData, setChartData] = useState<ChartData>();
  const workerRef = useRef<Worker | null>(null);

  useEffect(() => {
    workerRef.current = new MyWorker();
    return () => {
      workerRef.current?.terminate();
    };
  }, []);

  useEffect(() => {
    const worker = workerRef.current;
    if (!worker) return;

    if (data === null) return;

    const handleMessage = (e: MessageEvent<{ status: Status; chartData: ChartData }>) => {
      setChartData(e.data.chartData);
    };

    worker.addEventListener("message", handleMessage);
    worker.postMessage({ data, sorted });

    return () => {
      worker.removeEventListener("message", handleMessage);
    };
  }, [data, sorted]); // No worker in deps; it's stable in the ref

  if (data === null) {
    return undefined;
  }

  return chartData;
}

import { AggregateData, ChartData } from "@/interfaces";
import { useEffect, useState } from "react";

type Status = "loading" | "success" | "error";

export default function useCreateChartData(
  data: AggregateData | null,
  sorted: boolean = false,
): [ChartData | undefined, Status] {
  const [chartData, setChartData] = useState<ChartData>();
  const [status, setStatus] = useState<Status>("loading");
  const [worker, setWorker] = useState<Worker>();

  useEffect(() => {
    const worker = new Worker(new URL("./createChartDataWorker.ts", import.meta.url));
    setWorker(worker);
    return () => {
      worker.terminate();
    };
  }, []);

  useEffect(() => {
    if (data === null) {
      setChartData(undefined);
      setStatus("success");
      return;
    }
    if (worker != null && window.Worker !== undefined) {
      setStatus("loading");
      worker.onmessage = (e: MessageEvent<{ status: Status; chartData: ChartData }>) => {
        try {
          setChartData(e.data.chartData);
          setStatus(e.data.status);
        } catch (e) {
          setChartData(undefined);
          setStatus("error");
        }
      };
      worker.postMessage({ data, sorted });
    }
  }, [data, sorted, worker]);

  return [chartData, status];
}

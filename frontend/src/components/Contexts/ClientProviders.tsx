import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { ThemeProvider } from "next-themes";
import { useState } from "react";
import { toast } from "sonner";
import { ZodError } from "zod";
import { fromZodError } from "zod-validation-error";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthSessionProvider } from "@/components/Contexts/AuthProvider";
import { AxiosError } from "axios";
import { NuqsAdapter } from "nuqs/adapters/tanstack-router";

const defaultOptions = {
  queries: {
    retry: (failureCount: number, e: Error) => {
      if (failureCount >= 2) return false;
      if (!(e instanceof AxiosError)) return false;
      const unauthorized = e.response?.status == 401;
      const forbidden = e.response?.status == 403;
      const zodError = e.name === "ZodError";
      const doRetry = !zodError && !unauthorized && !forbidden;
      return doRetry;
    },
    cacheTime: 1000 * 60 * 60,
    staleTime: 1000 * 60 * 5, // the lower the better the UX, but the higher the server load
  },
};

function zodErrorToast(e: ZodError) {
  const zoderror = fromZodError(e);
  toast.error("Invalid payload", { description: String(zoderror) });
}

type ApiError = AxiosError<{ detail?: string; message?: string }>;

function defaultErrorToast(e: ApiError) {
  const msg = e?.response?.data?.detail || e?.response?.data?.message || e.message;
  if (msg) {
    const description = typeof msg === "string" ? msg : JSON.stringify(msg, null, 2);
    toast.error(description);
  } else {
    toast.error(e.message);
  }
}

export default function ClientProviders({ children }: { children: React.ReactNode }) {
  // allow signing in to local server on specific port. Useful for development,
  // or for running local amcat without having to run a new client
  //const [port] = useState(() => params?.get("port"));

  const mutationCache = new MutationCache({
    onError: (e: Error) => {
      console.error(e);

      if (e instanceof ZodError) {
        zodErrorToast(e);
      } else if (e instanceof AxiosError) {
        defaultErrorToast(e);
      } else {
        toast.error(e.message);
      }
      return e;
    },
  });
  const queryCache = new QueryCache({
    onError: (e: Error) => {
      console.error(e);

      if (e instanceof ZodError) {
        zodErrorToast(e);
      } else if (e instanceof AxiosError) {
        defaultErrorToast(e);
      } else {
        toast.error(e.message);
      }
      return e;
    },
  });
  const [queryClient] = useState(() => new QueryClient({ mutationCache, queryCache, defaultOptions }));

  function renderIfLoaded() {
    return (
      <>
        <AuthSessionProvider>
          <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
        </AuthSessionProvider>
        <ReactQueryDevtools initialIsOpen={false} />
      </>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <NuqsAdapter>{renderIfLoaded()}</NuqsAdapter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

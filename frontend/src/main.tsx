import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import "./app/globals.css";
import { AuthSessionProvider } from "./components/Contexts/AuthProvider";
import { TooltipProvider } from "./components/ui/tooltip";
import { NuqsAdapter } from "nuqs/adapters/tanstack-router";
import ReactQueryProvider from "./components/Contexts/ReactQueryProvider";
import { ThemeProvider } from "./components/Contexts/ThemeProvider";

// Create a new router instance
const router = createRouter({ routeTree });

// Register the router instance for type safety
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

function App() {
  useEffect(() => {
    const loader = document.getElementById("loading-screen");
    const bar = document.getElementById("loading-bar");
    if (loader && bar) {
      bar.style.width = "100%";
      bar.style.animation = "progress 0.2s ease-in-out";
      loader.classList.add("loading-fade-out");
      const removeTimeout = setTimeout(() => {
        loader.remove();
      }, 200);
      return () => {
        clearTimeout(removeTimeout);
      };
    }
  }, []);

  return (
    <ReactQueryProvider>
      <AuthSessionProvider>
        <TooltipProvider delayDuration={300}>
          <NuqsAdapter>
            <ThemeProvider>
              <RouterProvider router={router} />
            </ThemeProvider>
          </NuqsAdapter>
        </TooltipProvider>
      </AuthSessionProvider>
    </ReactQueryProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

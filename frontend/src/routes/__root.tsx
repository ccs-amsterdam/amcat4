import { createRootRoute, Outlet } from "@tanstack/react-router";
import Navbar from "@/components/Menu/Navbar";
import { Toaster } from "@/components/ui/sonner";
import { TanStackRouterDevtools } from "@tanstack/react-router-devtools";

export const Route = createRootRoute({
  component: () => (
    <div className="no-scrollbar relative flex min-h-screen flex-col scroll-smooth">
      <Navbar />
      <Outlet />
      <Toaster />
      <TanStackRouterDevtools />
    </div>
  ),
});

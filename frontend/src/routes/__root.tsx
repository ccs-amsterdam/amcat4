import { createRootRoute, Outlet } from "@tanstack/react-router";
import Navbar from "@/components/Menu/Navbar";
import { Toaster } from "@/components/ui/sonner";
import { TanStackRouterDevtools } from "@tanstack/react-router-devtools";
import OnboardingTour from "@/components/Onboarding/OnboardingTour";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

function RootComponent() {
  const { user } = useAmcatSession();
  return (
    <div className="no-scrollbar relative flex min-h-screen flex-col scroll-smooth">
      <Navbar />
      <Outlet />
      <Toaster />
      <OnboardingTour user={user} />
      <TanStackRouterDevtools />
    </div>
  );
}

export const Route = createRootRoute({
  component: RootComponent,
});

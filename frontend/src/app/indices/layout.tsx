"use client";
import { useAmcatConfig } from "@/api/config";

import { Button } from "@/components/ui/button";
import { ErrorMsg } from "@/components/ui/error-message";
import { LogInIcon } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAmcatSession();
  const { data: config } = useAmcatConfig();
  // const { data: userDetails } = useCurrentUserDetails(user);

  if (user && !user.authenticated && config?.authorization === "allow_authenticated_guests")
    return <AuthenticatedOnlyServer />;

  return (
    <>
      <div className="flex h-full w-full flex-auto flex-col pt-6 md:pt-6">
        <div className="flex h-full justify-center">
          <div className="flex w-full max-w-[1500px] flex-col px-5 py-5 sm:px-10">{children}</div>
        </div>
      </div>
    </>
  );
}

function AuthenticatedOnlyServer({}: {}) {
  const { signIn } = useAmcatSession();

  return (
    <ErrorMsg type="Sign-in required">
      <p className="w-[500px] max-w-[95vw] text-center">
        This server only allows authenticated users. Please sign-in to access the available indices.
      </p>
      <Button className="mx-auto flex items-center gap-2 pr-6" onClick={() => signIn()}>
        <LogInIcon className="mr-2 h-4 w-4" />
        Sign-in
      </Button>
    </ErrorMsg>
  );
}

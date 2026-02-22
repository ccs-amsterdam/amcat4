"use client";

import { ErrorMsg } from "@/components/ui/error-message";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useMyIndexrole } from "@/api";
import { useParams } from "next/navigation";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ index: string }>();
  const { user } = useAmcatSession();
  const indexRole = useMyIndexrole(user, params?.index);

  if (!indexRole) return <NoAccessToThisIndex />;

  return children;
}

function NoAccessToThisIndex() {
  // const { signIn } = useAmcatSession();

  return (
    <ErrorMsg type="No access">
      <p className="w-[500px] max-w-[95vw] text-center">You do not have access to this index</p>
    </ErrorMsg>
  );
}

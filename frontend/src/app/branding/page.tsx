"use client";

import { useAmcatBranding } from "@/api/branding";
import { useAmcatConfig } from "@/api/config";
import { Loading } from "@/components/ui/loading";
import { AmcatSessionUser, useAmcatSession } from "@/components/Contexts/AuthProvider";

import { Branding, BrandingFooter } from "@/components/Server/Branding";
import { AmcatBranding, AmcatConfig } from "@/interfaces";
import { ServerBrandingForm } from "@/components/Server/ServerBrandingForm";

export default function Page() {
  const { user } = useAmcatSession();
  const { data: serverConfig, isLoading: configLoading } = useAmcatConfig();
  const { data: serverBranding, isLoading: brandingLoading } = useAmcatBranding();
  if (configLoading || brandingLoading) return <Loading />;

  return (
    <div className="mx-auto mt-12 w-full max-w-7xl px-6 py-6">
      <ServerSettings user={user} serverConfig={serverConfig!} serverBranding={serverBranding!} />
    </div>
  );
}

interface ServerSettingsProps {
  user: AmcatSessionUser | undefined;
  serverConfig: AmcatConfig;
  serverBranding: AmcatBranding;
}

function ServerSettings({ user, serverConfig, serverBranding }: ServerSettingsProps) {
  return (
    <div className={`mx-auto grid max-w-[600px] grid-cols-1 gap-6 lg:max-w-full lg:grid-cols-2`}>
      <ServerBrandingForm />
      <ServerBrandingPreview user={user} serverConfig={serverConfig} serverBranding={serverBranding} />
    </div>
  );
}

function ServerBrandingPreview({ serverConfig, serverBranding }: ServerSettingsProps) {
  return (
    <div className="flex flex-col items-center justify-start">
      <div className="py-3 font-bold">Branding preview</div>
      <div className="-mt-12 scale-75 overflow-hidden rounded-lg">
        <Branding serverConfig={serverConfig!} serverBranding={serverBranding!} />
        <BrandingFooter serverBranding={serverBranding!} />
      </div>
    </div>
  );
}

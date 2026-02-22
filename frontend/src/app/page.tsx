"use client";

import Link from "next/link";

import { useAmcatConfig } from "@/api/config";
import { Button } from "@/components/ui/button";

import { useAmcatBranding } from "@/api/branding";
import { Branding, BrandingFooter } from "@/components/Server/Branding";
import { Loading } from "@/components/ui/loading";
import { ArrowRight, BarChart2, Search, Share } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

export default function Index() {
  const { data: serverConfig, isLoading: configLoading } = useAmcatConfig();
  const { data: serverBranding, isLoading: brandingLoading } = useAmcatBranding();

  if (configLoading || brandingLoading) return <Loading />;

  return (
    <>
      <main className="flex flex-grow flex-col">
        <Branding serverConfig={serverConfig} serverBranding={serverBranding} />
        <ReadyBanner />
        <BrandingFooter serverBranding={serverBranding} />
      </main>
    </>
  );
}

function FeatureCards() {
  return (
    <div className="container mx-auto px-4">
      {/*<h2 className="mb-12 text-center text-3xl font-semibold">Key Features</h2>*/}
      <div className="grid gap-8 md:grid-cols-3">
        <FeatureCard
          icon={<Search className="h-10 w-10 " />}
          title="Search"
          description="Create searchable text and multimedia repositories"
        />
        <FeatureCard
          icon={<BarChart2 className="h-10 w-10" />}
          title="Process"
          description="
       Enrich content with advanced preprocessing and analysis tools
        "
        />
        <FeatureCard
          icon={<Share className="h-10 w-10 " />}
          title="Share"
          description="Fine-grained access control for collaboration and open-science"
        />
      </div>
    </div>
  );
}

interface FeatureCardProps {
  icon: any;
  title: string;
  description: string;
}
function FeatureCard({ icon, title, description }: FeatureCardProps) {
  return (
    <div className="rounded-lg bg-gradient-to-t from-primary to-primary/90 p-6 text-primary-foreground shadow-md">
      <div className="mb-4 flex items-center gap-6">
        {icon}
        <h3 className=" text-xl font-semibold ">{title}</h3>
      </div>
      <div className="mt-auto text-left">
        <p>{description}</p>
      </div>
    </div>
  );
}
function ReadyBanner() {
  return (
    <section className="pb-20 pt-44">
      <div className="container mx-auto px-4 text-center">
        <h2 className="mb-4 text-3xl font-bold">AmCAT: Open, Accessible, Scalable</h2>
        <p className="mx-auto mb-8 max-w-3xl text-xl">
          AmCAT is a completely open and user friendly text storage and analysis system. Because it is built on
          ElasticSearch, it is highly scalable and extremely fast.
        </p>
        <Link href="https://amcat.nl/book/">
          <Button size="lg" variant="outline">
            Learn more
            <ArrowRight className="ml-2 h-5 w-5" />
          </Button>
        </Link>
        <div className="mt-16">
          <FeatureCards />
        </div>
      </div>
    </section>
  );
}

import { useAmcatBranding } from "@/api/branding";
import { AmcatBranding } from "@/interfaces";
import {
  Bot,
  ChevronRight,
  Columns3Cog,
  DatabaseZap,
  Home,
  LayoutDashboard,
  Library,
  LockKeyholeOpen,
  Paintbrush,
  Settings,
  Slash,
  Users,
} from "lucide-react";
import { Link, useParams, useNavigate, useLocation } from "@tanstack/react-router";
import AccountMenu from "./AccountMenu";
import ProjectMenu from "./ProjectMenu";
import { Notifications } from "./Notifications";
import { SubMenu, SubMenuPath } from "./SubMenu";

const serverSubMenuPaths: SubMenuPath[] = [
  { href: "", label: "Home", Icon: Home, minServerRole: "NONE" },
  { href: "projects", label: "Projects", Icon: Library, minServerRole: "NONE" },
  { href: "branding", label: "Branding", Icon: Paintbrush, minServerRole: "ADMIN" },
  { href: "users", label: "Server users", Icon: Users, minServerRole: "ADMIN" },
  { href: "api_keys", label: "API keys", Icon: Bot, minServerRole: "NONE" },
  { href: "access", label: "Server role", Icon: LockKeyholeOpen, minServerRole: "NONE" },
];

const indexSubMenuPaths: SubMenuPath[] = [
  { href: "dashboard", label: "Dashboard", Icon: LayoutDashboard, minIndexRole: "METAREADER" },
  { href: "data", label: "Data", Icon: DatabaseZap, minIndexRole: "WRITER" },
  { href: "fields", label: "Fields", Icon: Columns3Cog, minIndexRole: "WRITER" },
  { href: "settings", label: "Settings", Icon: Settings, minIndexRole: "ADMIN" },
  { href: "users", label: "Users", Icon: Users, minIndexRole: "ADMIN" },
  { href: "access", label: "Access", Icon: LockKeyholeOpen, minIndexRole: "NONE" },
];

export default function Navbar() {
  const params = useParams({ strict: false }) as any;
  const hasIndex = !!params?.project;
  const location = useLocation();
  const path = location.pathname;
  const { data: branding } = useAmcatBranding();

  function logo() {
    return (
      <Link to={"/"} className="flex h-14 items-center px-3">
        <img
          className={`mr-0 aspect-auto w-9 min-w-9 sm:w-10 `}
          src={branding?.server_icon || "/logo.png"}
          alt="AmCAT"
        />
      </Link>
    );
  }

  function submenu() {
    if (hasIndex) return <SubMenu paths={indexSubMenuPaths} basePath={`/projects/${params.project}`} />;
    if (path !== "/") return <SubMenu paths={serverSubMenuPaths} />;
    return null;
  }

  return (
    <nav className={`z-40   border-b border-primary/30 text-sm`}>
      <div className={`select-none overflow-hidden border-b border-primary/30  bg-background  `}>
        <div className="flex h-14 items-center justify-between">
          {logo()}
          <BreadCrumbs branding={branding} hasIndex={hasIndex} />
          <div className=" flex h-full  flex-1 items-center justify-end">
            <Notifications />
            <AccountMenu />
          </div>
        </div>
      </div>
      {submenu()}
    </nav>
  );
}

function BreadCrumbs({ branding, hasIndex }: { branding?: AmcatBranding; hasIndex: boolean }) {
  const location = useLocation();
  const path = location.pathname;
  const homepage = path === "/";

  const serverLinkLabel = branding?.server_name || "Server";

  return (
    <>
      <div className="hidden h-full items-center overflow-hidden  text-sm   sm:flex  md:text-lg">
        <BreadCrumbLink name={serverLinkLabel} href="/projects" active={!homepage && !hasIndex} />
        <ChevronRight className="h-4 w-4 min-w-4 flex-shrink opacity-50" />
        {/*<span className="text-primary/50">|</span>*/}
        {/*<span className=" text-xs text-foreground/50">/</span>*/}
        <ProjectMenu />
      </div>
      <div className="flex  flex-col items-start overflow-hidden py-1  pl-2 text-sm sm:hidden  md:text-base">
        <BreadCrumbLink name={serverLinkLabel} href="/projects" active={!homepage && !hasIndex} />
        <ProjectMenu />
      </div>
    </>
  );
}

function BreadCrumbLink({ name, href, active = true }: { name: string; href: string; active?: boolean }) {
  const navigate = useNavigate();
  return (
    <button
      className={`${active ? "font-medium" : "text-foreground/90"}
        flex h-full min-w-0  select-none items-center gap-1  text-ellipsis whitespace-nowrap border-primary  px-1 outline-none hover:font-semibold md:px-3`}
      onClick={() => navigate({ to: href })}
    >
      {name}
    </button>
  );
}

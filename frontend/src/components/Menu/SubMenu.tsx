import { useMyIndexrole } from "@/api/index";
import { useMyGlobalRole } from "@/api/userDetails";
import { AmcatUserRole } from "@/interfaces";
import { hasMinAmcatRole } from "@/lib/utils";
import { Ellipsis } from "lucide-react";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useParams, useLocation, useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../ui/dropdown-menu";

export type SubMenuPath = {
  href: string;
  label: string;
  Icon: React.ElementType;
  minIndexRole?: AmcatUserRole;
  minServerRole?: AmcatUserRole;
};

export function useSubMenuPaths(paths: SubMenuPath[]) {
  const { user } = useAmcatSession();
  const params = useParams({ strict: false }) as any;
  const indexId = decodeURI(params?.project || "");
  const globalRole = useMyGlobalRole(user);
  const { role: indexRole } = useMyIndexrole(user, indexId);

  const allowedPaths = useMemo(() => {
    return paths.filter((path) => {
      if (path.minServerRole && !hasMinAmcatRole(globalRole, path.minServerRole)) return false;
      if (path.minIndexRole && !hasMinAmcatRole(indexRole, path.minIndexRole)) return false;
      return true;
    });
  }, [paths, globalRole, indexRole]);

  return allowedPaths;
}

export function SubMenu({ basePath = "", paths }: { basePath?: string; paths: SubMenuPath[] }) {
  const allowedPaths = useSubMenuPaths(paths);

  return (
    <div className="grid grid-cols-[1fr,max-content] bg-primary/10 font-light text-foreground">
      <div className="flex h-9 w-full items-center justify-start   overflow-hidden text-sm">
        {allowedPaths.map((path, i) => (
          <NavLink key={path.href} i={i} basePath={basePath} path={path} />
        ))}
      </div>
      <BurgerMenu basePath={basePath} paths={allowedPaths} />
    </div>
  );
}

function BurgerMenu({ basePath, paths }: { basePath: string; paths: SubMenuPath[] }) {
  const navigate = useNavigate();
  const currentPath = useCurrentPath();

  return (
    <div className="block sm:hidden">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="flex h-full select-none items-center gap-1 whitespace-nowrap border-primary px-3 pr-4 outline-none hover:bg-primary/10">
            <Ellipsis className="h-4 w-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {paths.map((path) => (
            <DropdownMenuItem
              key={path.href}
              onClick={() => navigate({ to: `${basePath}/${path.href}` })}
              className={`flex items-center gap-3 ${path.href === currentPath ? "bg-primary font-normal text-primary-foreground" : ""}`}
            >
              {<path.Icon className="h-4 w-4" />}
              <span>{path.label}</span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function useCurrentPath() {
  const location = useLocation();
  const path = location.pathname;
  if (!path) return "";
  const pathParts = path.split("/");
  return pathParts[pathParts.length - 1] || "";
}

function NavLink({ i, basePath, path }: { i: number; basePath: string; path: SubMenuPath }) {
  const navigate = useNavigate();
  const currentPath = useCurrentPath();

  const active = path.href === currentPath;
  const href = `${basePath}/${path.href}`;

  return (
    <button
      onClick={() => navigate({ to: href })}
      className={`${
        active ? "bg-primary/10" : "bg-transparent text-foreground/80 hover:bg-primary/10"
      } ${i === 0 ? "" : ""} flex h-full select-none items-center gap-2 border-primary px-3 outline-none   `}
    >
      {<path.Icon className="h-4 w-4" />}
      <span className={`hidden sm:inline`}>{path.label}</span>
    </button>
  );
}

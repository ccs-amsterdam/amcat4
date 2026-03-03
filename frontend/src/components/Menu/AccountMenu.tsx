

import { useAmcatConfig } from "@/api/config";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AmcatConfig } from "@/interfaces";
import { AlertCircle, Bot, Loader, LogInIcon, LogOut, User } from "lucide-react";
import { AmcatSessionUser, useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useNavigate } from "@tanstack/react-router";
import ThemeToggle from "./ThemeToggle";

export default function AccountMenu() {
  const { user, signIn, signOut } = useAmcatSession();
  const { data: config, isLoading: loadingConfig } = useAmcatConfig();
  const navigate = useNavigate();
  function renderAuthStatus() {
    if (config?.authorization === "no_auth") return "Authorization disabled";
    if (!user) return "not signed in";
    if (!user.authenticated) return "not signed in";

    return (
      <div className="flex flex-nowrap items-center">
        <span title={user.email} className="max-w-[15rem] overflow-hidden overflow-ellipsis whitespace-nowrap">
          {user.email}
        </span>
      </div>
    );
  }

  function renderAuthButtons() {
    if (config?.authorization === "no_auth") return null;
    if (user?.authenticated) {
      return (
        <DropdownMenuItem onClick={() => signOut()}>
          <LogOut className="mr-3 h-5 w-5" />
          <span>Sign-out</span>
        </DropdownMenuItem>
      );
    } else {
      return (
        <DropdownMenuItem onClick={() => signIn()}>
          <LogInIcon className="mr-3 h-5 w-5" />
          <span>Sign-in</span>
        </DropdownMenuItem>
      );
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="h-full min-w-[2.5rem] px-3 outline-none hover:bg-primary/10 md:pr-6">
        <UserIcon user={user} config={config} className="h-8 w-8  text-primary" />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        side="bottom"
        sideOffset={13}
        className="mr-2  min-w-48 border-[1px] border-foreground"
      >
        <DropdownMenuLabel>{renderAuthStatus()}</DropdownMenuLabel>
        {renderAuthButtons()}
        <DropdownMenuItem onClick={() => navigate({ to: "/api_keys" })} className={user.authenticated ? "" : "hidden"}>
          <Bot className="mr-3 h-5 w-5" />
          <span>API Keys</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <ThemeToggle label={true} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserIcon({
  user,
  config,
  className,
}: {
  user: AmcatSessionUser | undefined;
  config: AmcatConfig | undefined;
  className: string;
}) {
  if (config) {
    if (config.authorization === "no_auth") return <AlertCircle className={className} />;
  }

  if (user?.loading) return <Loader className={`${className} animate-[spin_6000ms_linear_infinite]`} />;

  // if (!user?.authenticated) return <LogInIcon className={className} />;
  if (!user?.authenticated) return <div className="">sign-in</div>;

  return (
    <div className="flex items-center gap-2">
      {/*<span className="hidden md:inline">{user.email}</span>*/}
      <User className={className} />
    </div>
  );
}

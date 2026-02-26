import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AmcatProject } from "@/interfaces";
import { randomIcon, randomLightColor } from "@/lib/utils";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { Link } from "@tanstack/react-router";
import { useConfirm } from "../ui/confirm";
import { ProjectDropdownMenu } from "./ProjectDropdownMenu";
import { ReactElement } from "react";

export const ProjectCard = ({
  project,
  folders,
  toFolder,
}: {
  project: AmcatProject;
  folders: string[];
  toFolder: (folder: string) => void;
}) => {
  const { activate, confirmDialog } = useConfirm();
  const { user } = useAmcatSession();
  if (user == null) return null;

  const hasImage = !!project.image_url;

  const style = {
    backgroundImage: `url('${hasImage ? project.image_url : ""}')`,
    backgroundRepeat: "no-repeat",
    backgroundPositionX: "center",
    backgroundSize: hasImage ? "cover" : "80px",
    backgroundColor: hasImage ? "" : randomLightColor(project.id),
    backgroundPositionY: "center",
  };

  const Icon = hasImage ? null : (randomIcon(project.id) as any);

  return (
    <>
      {confirmDialog}
      <Link to={`/projects/${project.id}/dashboard`}>
        <Card
          style={style}
          className="relative aspect-video w-full max-w-[400px] animate-fade-in justify-self-end  overflow-hidden  shadow-md"
        >
          <div
            className={`group h-full w-full ${hasImage ? "bg-gradient-to-b from-black/90 via-black/30 to-transparent" : "rounded-md border-4 border-foreground/10 bg-gradient-to-br from-black/30 to-black/20"}    `}
          >
            <CardHeader className="flex h-full  flex-col justify-between p-0">
              <div className="flex items-start justify-between  p-3 text-white">
                <CardTitle className={`line-clamp-2 text-base leading-5 `}>{project.name}</CardTitle>
                <ProjectDropdownMenu
                  project={project}
                  folders={folders}
                  toFolder={toFolder}
                  activateConfirm={activate}
                />
              </div>
              <CardDescription className="h-16 overflow-hidden break-words rounded-b-md     bg-black/50 px-3 text-sm leading-4 text-white backdrop-blur-[2px] transition-all group-hover:line-clamp-4 group-hover:opacity-100 md:opacity-70">
                <div className="my-2 line-clamp-3">{project.description || ""}</div>
              </CardDescription>
            </CardHeader>

            {!Icon ? null : <Icon className="absolute bottom-3 right-3 m-auto h-20 w-20 text-white opacity-30" />}
          </div>
        </Card>
      </Link>
    </>
  );
};

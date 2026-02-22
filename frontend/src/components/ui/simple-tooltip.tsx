import { TooltipTrigger, Tooltip, TooltipContent } from "./tooltip";

export default function SimpleTooltip(props: { children: React.ReactNode; text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{props.children}</TooltipTrigger>
      <TooltipContent className="bg-secondary text-secondary-foreground" sideOffset={5} side="top" align="center">
        {props.text}
      </TooltipContent>
    </Tooltip>
  );
}

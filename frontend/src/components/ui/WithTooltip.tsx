import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { HelpCircle } from "lucide-react";

interface Props {
  children?: React.ReactNode;
  tooltip: React.ReactNode;
  open?: boolean;
  setOpen?: (open: boolean) => void;
}

export function WithTooltip({ children, tooltip }: Props) {
  const trigger = children ?? <HelpCircle className="mb-0 h-5 w-5 text-gray-600" />;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{trigger}</TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}

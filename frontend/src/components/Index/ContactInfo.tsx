import { contactInfoSchema } from "@/schemas";
import { Globe, User } from "lucide-react";
import { Fragment } from "react";
import { z } from "zod";

export function ContactInfo({ contact }: { contact: z.infer<typeof contactInfoSchema> | null | undefined }) {
  if (!contact || contact.length === 0)
    return (
      <div>
        <i>This index does not have public contact information.</i>
      </div>
    );
  return (
    <div className="grid grid-cols-[10px,auto,auto] items-center gap-x-6 gap-y-1">
      {contact.map(({ name, email, url }) => (
        <Fragment key={name + "." + email + "." + url}>
          <User className="h-5 w-5 text-foreground/60 " />
          <div>
            {email ? (
              <a href={`mailto:${email}`} className="underline" target="_blank" rel="noreferrer">
                {name || "Contact"}
              </a>
            ) : (
              name || "Contact"
            )}
          </div>
          <div>
            {url && (
              <a href={url} className="text-sm text-primary no-underline " target="_blank" rel="noreferrer">
                <Globe className="inline h-4 w-4" /> <span className="">{url.replace(/(^\w+:|^)\/\//, "")}</span>
              </a>
            )}
          </div>
        </Fragment>
      ))}
    </div>
  );
}

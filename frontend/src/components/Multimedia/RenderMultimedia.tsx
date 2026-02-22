import { useMultimediaPresignedGet } from "@/api/multimedia";
import { MultimediaType } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { Loading } from "../ui/loading";
import { extensionMapping } from "./MultimediaUpload";

export default function RenderMultimedia({
  user,
  indexId,
  url,
  renderAs,
  height,
}: {
  user: AmcatSessionUser;
  indexId: string;
  url: string;
  // if renderAs is given it will always render the url for this type. If not, it will use the
  // MINIO mimetype (if url is a key) or try to infer it from the url.
  renderAs?: MultimediaType;
  height?: number;
}) {
  const key = /https?:\/\//.test(url) ? undefined : url;
  const externalUrl = /https?:\/\//.test(url) ? url : undefined;
  const { data: presigned, isLoading } = useMultimediaPresignedGet(user, indexId, key);

  if (isLoading) return <Loading />;

  function getType() {
    if (renderAs) return renderAs;

    let mime: string = "";
    if (presigned?.content_type) {
      mime = presigned.content_type.join(" ") || "";
    } else {
      const ext = url.split(".").pop();
      if (ext) mime = extensionMapping[ext];
    }

    if (/video/.test(mime)) return "video";
    if (/image/.test(mime)) return "image";
    if (/audio/.test(mime)) return "audio";

    // default to image
    return "image";
  }

  function render() {
    const type = getType();
    if (externalUrl) return <RenderLink type={type} />;
    if (!presigned) return <InvalidLink />;

    if (type === "video") return <RenderVideo url={presigned.url} height={height} />;
    if (type === "audio") return <RenderAudio url={presigned.url} height={height} />;
    if (type === "image") return <RenderImage url={presigned.url} height={height} />;
    return null;
  }

  const link = presigned?.url || externalUrl;

  return (
    <a
      key={url}
      href={link}
      target="_blank"
      rel="noreferrer"
      className="m-0 flex flex-col rounded border border-primary no-underline"
    >
      <span
        title={key}
        className=" rounded text-primary-foreground no-underline"
        style={{ textShadow: "0 0 5px black" }}
      ></span>
      <div className="w-full overflow-hidden text-ellipsis whitespace-nowrap bg-primary p-2 py-2 text-sm font-normal text-primary-foreground">
        {url}
      </div>
      {render()}
    </a>
  );
}

function InvalidLink() {
  return (
    <div className="relative m-0 flex items-center justify-center gap-2 rounded p-1 py-2 text-center ">
      This file does not exist on this index
    </div>
  );
}

function RenderLink({ type }: { type: MultimediaType }) {
  // we 'could' also render external urls (hotlinking) but this is generally considered unethical,
  // and many websites will also block the request anyway. Better to just show a nice link.
  return <div className=" rounded p-1 py-2 text-center ">External {type}</div>;
}

interface RenderProps {
  url: string;
  height?: number;
}

function RenderImage({ url, height }: RenderProps) {
  return (
    <img
      style={{ height }}
      className="relative m-0 aspect-auto flex-auto bg-gray-200 object-cover hover:object-contain"
      src={url}
    />
  );
}

function RenderVideo({ url, height }: RenderProps) {
  return (
    <video
      style={{ height }}
      className="relative m-0 aspect-auto object-cover hover:object-contain"
      src={url}
      controls
    />
  );
}

function RenderAudio({ url, height }: RenderProps) {
  return (
    <audio
      style={{ height }}
      className="relative m-0 aspect-auto  object-cover hover:object-contain"
      src={url}
      controls
    />
  );
}

export function Loading({ msg }: { msg?: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center p-12 delay-300 duration-500 animate-in fade-in fill-mode-both">
      <span className="spike-loader"></span>
      <h2 className="mt-3 animate-pulse text-xl font-bold">{msg || "Loading"}</h2>
    </div>
  );
}

export function Loading({ msg }: { msg?: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center p-12">
      <span className="spike-loader"></span>
      <h2 className="mt-3 text-2xl font-bold">{msg || "Loading..."}</h2>
    </div>
  );
}

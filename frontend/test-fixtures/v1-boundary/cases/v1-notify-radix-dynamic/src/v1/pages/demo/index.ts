export async function load() {
  const { Toast } = await import("radix-ui");
  return Toast.Root;
}

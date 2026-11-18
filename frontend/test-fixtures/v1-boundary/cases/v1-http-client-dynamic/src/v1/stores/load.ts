export const load = async (url: string) =>
  (await import("axios")).default.get(url);

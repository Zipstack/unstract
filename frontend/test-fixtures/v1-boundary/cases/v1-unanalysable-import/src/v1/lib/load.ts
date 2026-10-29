export const load = (name: string): Promise<unknown> => import(name);

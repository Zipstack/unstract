import { http } from "@v1/services/http";

export const load = (url: string) => http.get(url);

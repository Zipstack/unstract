import { http } from "../../services/http";

export const load = (url: string) => http.get(url);

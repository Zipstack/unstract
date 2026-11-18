import axios from "axios";

export const load = (url: string) => axios.get(url);

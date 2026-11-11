import { legacy } from "./legacy.js";

legacy();
import("@v1/pages/demo/index.ts").then((page) => page.render());

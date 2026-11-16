import clsx from "clsx";
import { legacy } from "./legacy.js";

document.body.className = clsx("v0", legacy());
import("@v1/pages/demo/index.ts").then((page) => page.render());

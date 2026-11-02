import Logo from "@v1/assets/logo.svg?react";
import "@v1/styles/global.css";

// An asset, a stylesheet and import.meta.env, so the root typecheck must
// resolve them the way src/v1/tsconfig.json does.
export const mountV1 = (): string => `${import.meta.env.MODE}:${typeof Logo}`;

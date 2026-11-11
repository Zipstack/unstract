export const render = () =>
  import("../../../legacy.js").then(({ legacy }) => legacy());

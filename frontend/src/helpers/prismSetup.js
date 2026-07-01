import Prism from "prismjs";

// prismjs language/plugin add-ons (`prismjs/components/*`, `prismjs/plugins/*`)
// reference a *bare global* `Prism` and carry no import edge back to prismjs
// core. Under the Vite (ESM + code-split) build there is no guarantee the plain
// side-effect `import "prismjs"` evaluates — and installs that global — before
// those add-ons run, so they threw `ReferenceError: Prism is not defined`,
// crashing Combined Output (Prompt Studio detail page + HITL review).
//
// Import THIS module before any add-on: it is a real dependency edge whose
// `Prism` binding is used below (so it survives tree-shaking, unlike a bare
// side-effect import), and its body pins core on the global. A sibling
// dependency is fully evaluated — body included — before the next one, so the
// global is guaranteed to exist by the time the add-on modules evaluate.
if (!globalThis.Prism) {
  globalThis.Prism = Prism;
}

export default Prism;

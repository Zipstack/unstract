import Prism from "prismjs";

// The prismjs add-ons imported alongside this module (`prismjs/components/*`,
// `prismjs/plugins/*`) register their grammars onto a *bare global* `Prism` and
// carry no import edge back to prismjs core. Leaving that global to prismjs
// core's own self-install is unreliable under Vite's code-split production
// build: the add-ons evaluated before anything installed `Prism`, throwing
// `ReferenceError: Prism is not defined` and blanking Combined Output (Prompt
// Studio detail page + HITL review).
//
// Make it deterministic: the used `Prism` binding forces the bundler to retain
// and evaluate core, and this module — imported before the add-ons — pins it on
// the global so it exists by the time they register. Assign unconditionally:
// the global must be THIS instance, the one the add-ons extend and that
// JsonView's `Prism.highlightAll()` reads. A `!globalThis.Prism` guard could
// leave a different, pre-existing Prism in place and silently drop highlighting.
globalThis.Prism = Prism;

export default Prism;

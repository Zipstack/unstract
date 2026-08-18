import Prism from "prismjs";

// The prismjs language/plugin add-ons used across the app (`prismjs/components/*`,
// `prismjs/plugins/*`) register their grammars onto a *bare global* `Prism` and
// carry no import edge back to prismjs core. Under Vite's code-split production
// build those add-ons get hoisted into a shared chunk (Combined Output *and* the
// manual-review ResultEditor both import `prism-json`), which can evaluate before
// any per-component setup runs — so they threw `ReferenceError: Prism is not
// defined`, blanking the Prompt Studio detail page and the HITL review page.
//
// This module is imported EAGERLY from the app entry (`index.jsx`) so the global
// is installed at bootstrap, before any lazy chunk — including the shared one
// holding the add-ons — can load. Assign unconditionally: the global must be THIS
// instance, the one the add-ons extend and that `Prism.highlightAll()` reads; a
// `!globalThis.Prism` guard could leave a different, pre-existing Prism in place
// and silently drop highlighting. The used `Prism` binding also keeps the bundler
// from tree-shaking core away.
globalThis.Prism = Prism;

export default Prism;

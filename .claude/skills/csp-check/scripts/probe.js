/**
 * Browser-side CSP probe.
 *
 * Paste the whole file as the `function` argument of the chrome-devtools MCP
 * `evaluate_script` tool while a page from the target deployment is selected, with the
 * output of `extract_policy.py --json` inlined as DIRECTIVES below.
 *
 * It loads one throwaway resource per (directive, host) pair and records what the live
 * policy reports, so it answers two questions the config file alone cannot:
 *   1. does the deployment actually serve the policy we think it does?
 *   2. is each host allowed on the directive that will really load it?
 * Four control probes must always be reported -- if they are not, CSP is not applied.
 *
 * Note: CSP evaluates redirect targets. A probe path that 404-redirects to another host
 * (https://hooks.stripe.com/ -> https://stripe.com) reports that target, not a real gap.
 */
async () => {
  const DIRECTIVES = {
    /* paste extract_policy.py --json "directives" here */
  };

  const KIND_BY_DIRECTIVE = {
    "script-src": "script",
    "style-src": "style",
    "img-src": "img",
    "font-src": "font",
    "connect-src": "connect",
    "frame-src": "frame",
    "media-src": "media",
    "worker-src": "worker",
  };

  const probes = [];
  for (const [directive, sources] of Object.entries(DIRECTIVES)) {
    const kind = KIND_BY_DIRECTIVE[directive];
    if (!kind) continue;
    for (const source of sources) {
      if (!source.startsWith("https://")) continue;
      probes.push([kind, source.replace(/\/$/, "") + "/__csp_probe", false]);
    }
  }
  for (const kind of ["img", "connect", "script"]) {
    probes.push([kind, "https://csp-control.invalid/__csp_probe", true]);
  }
  probes.push(["connect", "wss://csp-control.invalid/__csp_probe", true]);

  const hits = [];
  const onViolation = (e) =>
    hits.push({
      directive: e.effectiveDirective || e.violatedDirective,
      blocked: e.blockedURI,
    });
  document.addEventListener("securitypolicyviolation", onViolation);
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  const load = (kind, url) => {
    if (kind === "script") {
      const el = document.createElement("script");
      el.src = url;
      document.head.appendChild(el);
    } else if (kind === "style") {
      const el = document.createElement("link");
      el.rel = "stylesheet";
      el.href = url;
      document.head.appendChild(el);
    } else if (kind === "img") {
      new Image().src = url;
    } else if (kind === "font") {
      new FontFace("cspProbe", `url(${url})`).load().catch(() => {});
    } else if (kind === "connect") {
      if (url.startsWith("wss:")) new WebSocket(url);
      else fetch(url, { mode: "no-cors" }).catch(() => {});
    } else if (kind === "frame") {
      const el = document.createElement("iframe");
      el.src = url;
      el.style.display = "none";
      document.body.appendChild(el);
    } else if (kind === "media") {
      const el = document.createElement("video");
      el.src = url;
      document.body.appendChild(el);
      el.load();
    } else if (kind === "worker") {
      new Worker(url);
    }
  };

  const expected = [];
  for (const [kind, url, isControl] of probes) {
    try {
      load(kind, url);
    } catch (e) {
      /* cross-origin Worker/WebSocket constructors can throw; CSP still reports first */
    }
    if (isControl) expected.push(url);
    await wait(250);
  }
  await wait(3000);
  document.removeEventListener("securitypolicyviolation", onViolation);

  const reported = new Set(hits.map((h) => h.blocked));
  return {
    // Hosts the policy is supposed to allow but the deployment still blocks.
    unexpected: hits.filter((h) => !h.blocked.includes("csp-control.invalid")),
    // Empty means CSP is live and restrictive. Non-empty means it is not applied at all.
    controlsNotReported: expected.filter(
      (url) => !reported.has(url) && !reported.has(new URL(url).origin)
    ),
    probeCount: probes.length,
  };
};

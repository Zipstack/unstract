---
name: csp-check
description: >
  Check the frontend Content-Security-Policy in frontend/nginx.conf against what the app
  actually loads. The policy is enforced, so a host it does not list is blocked. Use when
  adding or upgrading a third-party frontend dependency (CDN, analytics, payments,
  widgets), when a feature loads assets from a new external host, when a CSP violation
  shows up in the browser console, or when something works in `bun run dev` but breaks
  behind nginx.
---

# CSP Check

The frontend ships an enforcing `Content-Security-Policy` header from
`frontend/nginx.conf`. A resource from an origin no directive lists is **blocked** — whatever needed it breaks, and the only trace is a
console violation. So the policy has to be widened in the same change that adds the
dependency, not after someone reports a broken page.

There is no report collector: violations reach each user's browser console and nowhere
else. These checks are the only way to see a gap before a user does. Note the header is
only served by the production nginx image — `bun run dev` has no CSP at all, so "it worked
locally" says nothing.

Three checks, cheapest first. Run 1 on every change that touches a frontend dependency;
run 2 and 3 before widening the policy or shipping a new third-party integration.

## 1. Static: does the bundle reference a host the policy never allows?

```bash
cd .claude/skills/csp-check/scripts
python3 extract_policy.py                                  # what the policy says today
python3 scan_origins.py --url https://us-central.unstract.com
python3 scan_origins.py --dist                             # after `bun run build`
```

Bare `--dist` resolves the repo's own `frontend/build`, from any directory. Give it a path
only for a build somewhere else — and note the path is relative to your shell, not to the
script. The script exits non-zero when `--dist` is missing or holds no `.js`, when a
`--url` index names no bundle, and when a chunk `index.html` links fails to fetch; a 404
on a path found only inside a bundle string is tolerated, since that is usually a worker
path a chunk names but never loads. Check the file count on the first output line against
what the build produced.

`scan_origins.py` pulls every `/assets/*.js|css` chunk (following relative imports), plus
`index.html` and the entrypoint-generated `/config/runtime-config.js`, extracts external
`https://` URLs, and exits non-zero on any the policy would block. Hosts that only appear
in doc links, XML namespaces and library error strings are listed in its `IGNORED` set —
extend it rather than widening the policy for a host nothing fetches.

Verdicts: `MISSING` (no fetch directive names the host — `form-action`, `base-uri` and
`frame-ancestors` do not count, since nothing can be loaded on their strength), `PATH`
(listed path-scoped and this URL falls outside it — `https://www.google.com/recaptcha/`
grants that path only, so `https://www.google.com/g/collect` is still blocked) and `PORT`
(a source with no port grants 443 only). `*.` sources match subdomains only, the way the
browser reads them: `https://*.google-analytics.com` covers `region1.google-analytics.com`
but not a bare `google-analytics.com`.

This catches "a new dependency pulls from a new CDN". It cannot tell you *which*
directive loads a host — a font from a script-src-only host still violates. That is check 2.

What it still cannot see: a URL assembled at runtime, and a URL supplied by deployment
config. `VITE_CUSTOM_LOGO_URL` / `VITE_FAVICON_PATH` are the live example — see
"Operator-supplied URLs" below.

## 2. Live: probe the deployed policy, directive by directive

With the chrome-devtools MCP on a page of the target deployment:

1. `python3 extract_policy.py --json` and paste `directives` into `DIRECTIVES` in
   `scripts/probe.js`.
2. Run the whole file as the `function` argument of `evaluate_script`.

It loads one throwaway resource per (directive, host) pair and returns:

- `unexpected` — hosts the policy is meant to allow but the deployment still reports.
  Non-empty means the running deployment does not serve the policy in this repo, or the
  host is allowed on the wrong directive.
- `controlsNotReported` — must be empty. Non-empty means CSP is not being applied at all.

A wildcard source is probed as `csp-probe.<suffix>`, because `https://*.example.com/…` is
not a hostname and the request would die before CSP saw it. CSP is evaluated before DNS —
which is why the `csp-control.invalid` controls get reported without resolving — so a
`csp-probe.*` entry in `unexpected` means the deployment is not serving that wildcard.

CSP evaluates **redirect targets**: a probe path that 404-redirects to another host
(`https://hooks.stripe.com/` → `https://stripe.com`) reports the target, not a real gap.

## 3. Real usage: collect violations while driving the app

Probes only test hosts already in the policy. To find what a feature loads that nobody
listed, record violations while using it. Navigate with this `initScript` (chrome-devtools
`navigate_page`), which survives SPA route changes:

```js
document.addEventListener('securitypolicyviolation', (e) => {
  const k = '__cspAll';
  const prev = JSON.parse(sessionStorage.getItem(k) || '[]');
  prev.push({dir: e.effectiveDirective || e.violatedDirective, blocked: e.blockedURI,
             src: (e.sourceFile || '') + ':' + (e.lineNumber || ''), page: location.pathname});
  sessionStorage.setItem(k, JSON.stringify(prev.slice(-400)));
});
```

Then walk the feature and read `JSON.parse(sessionStorage.getItem('__cspAll'))`. SPA routes
can be walked without reloading:
`history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate'))`.

Third-party widgets load lazily and per-plan, so exercise the actual flow — an integration
that never initialises reports nothing.

## Operator-supplied URLs

`generate-runtime-config.sh` writes `/config/runtime-config.js` at container start from
`VITE_CUSTOM_LOGO_URL` / `VITE_FAVICON_PATH` (and their `REACT_APP_*` fallbacks). Both
end up governed by `img-src`: the logo through `<Image src>` in `TopNavBar.jsx`, the
favicon through `setFavicon` in `index.jsx`.

**They must be same-origin paths** (`/config/logo.svg`), not absolute URLs on another
host. An absolute URL to a host the policy does not list is blocked once the header
enforces, and both failures are quiet — the logo's `onError` swaps in the default mark
and the favicon just stays the old one. No build-time scan can catch it, because the
value does not exist until the container starts.

An operator who must serve branding from their own CDN has to add that host to `img-src`
in `frontend/nginx.conf` and rebuild the frontend image.

The same shape, not live today: `sessionDetails.picture` is an absolute avatar URL the
auth backend may supply, rendered by `<Image src>` in `TopNavBar.jsx` and in the
subscription-end plugin page. Neither `account_v2.AuthenticationService.get_user_info`
nor the cloud Auth0 plugin's populates it — the Auth0 models parse `picture` from the IdP
token but never carry it into `UserInfo` — so the initials branch always renders and no
IdP host is in `img-src`. If that ever changes, the avatar is blocked, and because
`picture` would then be truthy the component shows a broken-image placeholder rather than
falling back to initials. Whoever fills that field adds the IdP host here.

**The general rule:** any URL that arrives at runtime — deployment config, an API
response, an IdP token — is invisible to checks 1 and 2 and only shows up in check 3, and
then only if the account you drive the app with actually has the value set.

## Changing the policy

Edit the single `add_header Content-Security-Policy` line in `frontend/nginx.conf`. Keep
it one line: nginx accepts multi-line quoted strings, but the newlines end up in the
header value.

Verify before pushing — nginx will start with a malformed policy and browsers will silently
drop the bad directive:

```bash
docker run -d --name csp-probe -p 8899:80 \
  -v "$PWD/frontend/nginx.conf:/etc/nginx/nginx.conf:ro" nginx:alpine
curl -sI http://localhost:8899/ | grep -i content-security-policy
```

Then point check 2 at `http://localhost:8899/` to confirm the new policy allows what it
should and still blocks the controls. `docker rm -f csp-probe` when done.

Which directive a host belongs in:

| Loaded as | Directive |
|---|---|
| `<script src>`, dynamic `import()` | `script-src` |
| `<link rel=stylesheet>`, `@import` | `style-src` |
| `<img>`, CSS `url()` background, tracking pixel | `img-src` |
| `@font-face`, `FontFace()` | `font-src` |
| `fetch`/XHR/`sendBeacon`/WebSocket | `connect-src` |
| `<iframe>` | `frame-src` |
| `<video>`/`<audio>` | `media-src` |
| `new Worker()` | `worker-src` |

A host loaded several ways needs an entry in each directive — that is the most common
miss. Path-scoped sources (`https://www.gstatic.com/recaptcha/`) keep the grant narrow and
are worth using when a vendor serves everything from one host.

## Notes

- `connect-src` carries no `wss:` wildcard. socket.io connects to `window.location.origin`
  (`frontend/src/helpers/GetStaticData.js` `getBaseUrl`) and `'self'` covers same-origin
  ws/wss per CSP3. Verified with a `ws://` probe against a local nginx serving the policy.
- The backend sends its own enforcing `Content-Security-Policy` from
  `backend/middleware/content_security_policy.py`. It applies to backend responses (JSON
  APIs, the OSS login page), not to the SPA — do not confuse the two when debugging.

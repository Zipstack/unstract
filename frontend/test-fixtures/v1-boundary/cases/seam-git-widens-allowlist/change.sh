mkdir -p src/v1/lib && echo "export const x = 1;" > src/v1/lib/x.ts
echo '// changed' >> src/pages/a.jsx
# Widen the allowlist in the same change (node, not `sed -i`, for macOS).
node -e '
const fs = require("node:fs");
const file = "scripts/v1-seam-allowlist.json";
const list = JSON.parse(fs.readFileSync(file, "utf8"));
list.allow.push("src/pages/**");
fs.writeFileSync(file, JSON.stringify(list, null, 2));
'
grep -q 'src/pages' scripts/v1-seam-allowlist.json

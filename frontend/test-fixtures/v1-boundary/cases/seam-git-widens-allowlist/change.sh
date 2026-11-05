mkdir -p src/v1/lib && echo "export const x = 1;" > src/v1/lib/x.ts
echo '// changed' >> src/pages/a.jsx
sed -i 's#"src/routes/\*\*",#"src/routes/**", "src/pages/**",#' scripts/v1-seam-allowlist.json
grep -q 'src/pages' scripts/v1-seam-allowlist.json

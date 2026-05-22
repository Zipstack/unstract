import { lazy, Suspense } from "react";

import { SpinnerLoader } from "../components/widgets/spinner-loader/SpinnerLoader.jsx";

// Cloud-only plugin. OSS-only deployments don't have the file; the route is
// also gated on a successful dynamic-import probe in SideNavBar.jsx so this
// component should never be reached without the cloud build in place.
const IdpGroupImport = lazy(() =>
  import("../plugins/idp-group-import/IdpGroupImport.jsx").then((mod) => ({
    default: mod.IdpGroupImport,
  })),
);

function IdpGroupImportPage() {
  return (
    <Suspense fallback={<SpinnerLoader />}>
      <IdpGroupImport />
    </Suspense>
  );
}

export { IdpGroupImportPage };

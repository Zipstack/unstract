import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import { PageTitle } from "../components/widgets/page-title/PageTitle.jsx";
import { MenuLayout } from "../layouts/menu-layout/MenuLayout.jsx";
import { useSessionStore } from "../store/session-store.js";

export function LookUpsPage() {
  const { updateSessionDetails } = useSessionStore();

  useEffect(() => {
    updateSessionDetails({ activeMenuId: "lookups" });
  }, [updateSessionDetails]);

  return (
    <>
      <PageTitle title="Look-Ups" />
      <MenuLayout>
        <Outlet />
      </MenuLayout>
    </>
  );
}

import { Route } from "react-router-dom";
import { LookUpsPage } from "../pages/LookUpsPage";
import { LookUpProjectList } from "../components/lookups/project-list/LookUpProjectList";
import { LookUpProjectDetail } from "../components/lookups/project-detail/LookUpProjectDetail";

export const useLookUpsRoutes = () => {
  return (
    <Route path="lookups" element={<LookUpsPage />}>
      <Route path="" element={<LookUpProjectList />} />
      <Route path=":projectId" element={<LookUpProjectDetail />} />
    </Route>
  );
};

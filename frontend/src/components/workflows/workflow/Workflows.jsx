import { PlusOutlined } from "@ant-design/icons";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useListManager } from "../../../hooks/useListManager";
import WorkflowModal from "./WorkflowModal";
import { ListView } from "../../view-projects/ListView";
import { workflowService } from "./workflow-service";

function Workflows() {
  const { setPostHogCustomEvent } = usePostHogEvents();
  const projectApiService = workflowService();

  const getListApiCall = ({ initialFilter }) =>
    projectApiService.getProjectList(initialFilter);

  const addItemApiCall = ({ itemData }) =>
    projectApiService.editProject(
      itemData?.name ?? "",
      itemData?.description ?? ""
    );

  const editItemApiCall = ({ itemData, itemId }) =>
    projectApiService.editProject(
      itemData?.name ?? "",
      itemData?.description ?? "",
      itemId
    );

  const deleteItemApiCall = ({ itemId }) =>
    projectApiService.deleteProject(itemId);

  const useListManagerHook = useListManager({
    getListApiCall,
    addItemApiCall,
    editItemApiCall,
    deleteItemApiCall,
    searchProperty: "workflow_name",
    itemIdProp: "id",
    itemNameProp: "workflow_name",
    itemDescriptionProp: "description",
    itemType: "Workflow",
    initialFilter: "mine",
  });

  return (
    <ListView
      title="Workflows"
      useListManagerHook={useListManagerHook}
      CustomModalComponent={WorkflowModal}
      customButtonText="New Workflow"
      customButtonIcon={<PlusOutlined />}
      itemProps={{
        titleProp: "workflow_name",
        descriptionProp: "description",
        idProp: "id",
        type: "Workflow",
      }}
      setPostHogCustomEvent={setPostHogCustomEvent}
      newButtonEventName="intent_new_wf_project"
    />
  );
}

export { Workflows };

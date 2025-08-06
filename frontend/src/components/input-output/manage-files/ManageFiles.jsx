import { useState, useEffect } from "react";
import PropTypes from "prop-types";

import { inputService } from "../../input-output/input-output/input-service.js";
import { FileExplorer } from "../file-system/FileSystem.jsx";

function ManageFiles({
  selectedConnector,
  onFolderSelect,
  selectedFolderPath,
}) {
  const inpService = inputService();

  const [files, setFiles] = useState([]);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setFiles([]);
    if (!selectedConnector) return;
    setLoadingData(true);
    inpService
      .getFileList(selectedConnector)
      .then((res) => {
        setFiles(res.data);
        setError(false);
      })
      .catch(() => {
        setError(true);
      })
      .finally(() => {
        setLoadingData(false);
      });
  }, [selectedConnector]);

  return (
    <FileExplorer
      selectedConnector={selectedConnector}
      data={files}
      loadingData={loadingData}
      error={error}
      onFolderSelect={onFolderSelect}
      selectedFolderPath={selectedFolderPath}
    />
  );
}

ManageFiles.propTypes = {
  selectedConnector: PropTypes.string,
  onFolderSelect: PropTypes.func,
  selectedFolderPath: PropTypes.string,
};

export { ManageFiles };

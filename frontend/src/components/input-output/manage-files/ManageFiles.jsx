import { useState, useEffect } from "react";
import PropTypes from "prop-types";

import { inputService } from "../../input-output/input-output/input-service.js";
import { FileExplorer } from "../file-system/FileSystem.jsx";

function ManageFiles({ selectedItem }) {
  const inpService = inputService();

  const [files, setFiles] = useState([]);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setFiles([]);
    if (!selectedItem) return;
    setLoadingData(true);
    inpService
      .getFileList(selectedItem)
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
  }, [selectedItem]);

  return (
    <FileExplorer
      selectedItem={selectedItem}
      data={files}
      loadingData={loadingData}
      error={error}
    />
  );
}

ManageFiles.propTypes = {
  selectedItem: PropTypes.string,
};

export { ManageFiles };

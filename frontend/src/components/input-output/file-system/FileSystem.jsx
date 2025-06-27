import { CaretDownOutlined } from "@ant-design/icons";
import { Tree, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useRef, useState } from "react";

import { Document, Folder } from "../../../assets";
import { formatBytes } from "../../../helpers/GetStaticData";
import { inputService } from "../../input-output/input-output/input-service.js";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";

import "./FileSystem.css";

const { DirectoryTree } = Tree;
const { Text } = Typography;

function FileExplorer({
  selectedItem = "",
  data = [],
  loadingData,
  error,
  onFolderSelect,
  selectedFolderPath,
}) {
  const inpService = inputService();

  const [tree, setTree] = useState([]);
  const [expandedKeys, setExpandedKeys] = useState([]);
  const [selectedKeys, setSelectedKeys] = useState([]);
  const [autoExpandParent, setAutoExpandParent] = useState(true);

  const uploadPathRef = useRef("");

  useEffect(() => {
    const treeData = structuredClone(data);
    updateTree(treeData);
  }, [data, loadingData, error]);

  useEffect(() => {
    // Clear selected items/keys when the data source is changed.
    setExpandedKeys([]);
    setSelectedKeys([]);
  }, [selectedItem]);

  function onLoadData({ key, children }) {
    return new Promise((resolve) => {
      if (children) {
        resolve();
        return;
      }
      getAndUpdateFiles(key)
        .then(() => {
          resolve();
        })
        .catch(() => {});
    });
  }

  function getAndUpdateFiles(path) {
    return inpService
      .getFileList(selectedItem, path)
      .then((res) => {
        let newTree = tree;
        if (path) {
          const targetNode = getTargetNode(path, newTree);
          targetNode["children"] = res.data;
        } else {
          newTree = res.data;
        }
        updateTree(newTree);
      })
      .catch(() => {
        console.error(
          `Unable to get files on "${selectedItem}" for the folder "${path}"`
        );
      });
  }

  function onSelect(selectedKeys, event) {
    setSelectedKeys(selectedKeys);
    if (event.node.isLeaf) {
      uploadPathRef.current = "";
    } else {
      uploadPathRef.current = event.node.key;
      // Call the folder selection callback if provided
      if (onFolderSelect) {
        onFolderSelect(event.node.key);
      }
    }
  }

  function onExpand(newExpandedKeys) {
    setExpandedKeys(newExpandedKeys);
    setAutoExpandParent(false);
  }

  function updateTree(treeData) {
    transformTree(treeData);
    setTree([...treeData]);
    setSelectedKeys([]);
  }

  return (
    <div className="storageExplorer">
      {tree.length !== 0 && (
        <>
          <div className="fileText fileHeading">
            <Text type="secondary" ellipsis strong>
              Name
            </Text>
            <Text type="secondary" ellipsis strong>
              Size
            </Text>
            <Text type="secondary" ellipsis strong>
              Modified at
            </Text>
          </div>
          <DirectoryTree
            rootClassName="explorerTree"
            showLine
            treeData={tree}
            switcherIcon={<CaretDownOutlined />}
            expandedKeys={expandedKeys}
            selectedKeys={selectedKeys}
            autoExpandParent={autoExpandParent}
            onExpand={onExpand}
            onSelect={onSelect}
            loadData={onLoadData}
            expandAction={false}
          />
        </>
      )}
      {loadingData && <SpinnerLoader />}
      {tree?.length === 0 && !error && (
        <div className="center">
          <Text>No files</Text>
        </div>
      )}
      {error && (
        <div className="center">
          <Text>Error loading the data</Text>
        </div>
      )}
    </div>
  );
}

FileExplorer.propTypes = {
  data: PropTypes.array,
};

function getTargetNode(key, treeData) {
  let targetNode;
  for (const node of treeData) {
    if (node.key === key) {
      targetNode = node;
      break;
    } else if (node.children) {
      const findTargetNode = getTargetNode(key, node.children);
      if (findTargetNode) {
        targetNode = findTargetNode;
        break;
      }
    }
  }
  return targetNode;
}

function transformTree(tree) {
  let key = "";
  let title = "";
  let isFile = "";
  let modifiedDate = "";
  let size = "";

  tree.forEach((node) => {
    key = node.name;
    title = key.split("/").at(-1);
    isFile = node.type === "file";
    modifiedDate = node.modified_at?.split(" ")[0] || "";
    size = isFile ? formatBytes(node.size) : "";

    node["key"] = key;
    node["icon"] = isFile ? <Document /> : <Folder />;
    node["title"] = (
      <div className="fileText">
        <Text ellipsis>{title}</Text>
        <Text>{size}</Text>
        <Text>{modifiedDate}</Text>
      </div>
    );
    node["isLeaf"] = isFile;

    if (node.children) {
      transformTree(node.children);
    }
  });
}

FileExplorer.propTypes = {
  selectedItem: PropTypes.string,
  data: PropTypes.array,
  loadingData: PropTypes.bool,
  error: PropTypes.bool,
  onFolderSelect: PropTypes.func,
  selectedFolderPath: PropTypes.string,
};

export { FileExplorer };

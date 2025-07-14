import { Col, Image, Row } from "antd";
import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";

import { CONNECTOR_TYPE_MAP } from "../../../helpers/GetStaticData.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { AddSourceModal } from "../add-source-modal/AddSourceModal.jsx";
import { ManageFiles } from "../manage-files/ManageFiles.jsx";
import { Sidebar } from "../sidebar/Sidebar.jsx";
import "./InputOutput.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
const INPUT = "input";
const OUTPUT = "output";

function InputOutput() {
  const [selectedItem, setSelectedItem] = useState();
  const [listOfItems, setListOfItems] = useState([]);
  const [openModal, setOpenModal] = useState(false);
  const [connectorType, setConnectorType] = useState("");
  const [reloadList, setReloadList] = useState(false);
  const [editItemId, setEditItemId] = useState(null);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const { id } = useParams();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const location = useLocation();
  const currentPath = location.pathname;

  const sourceIcon = (src) => {
    return <Image src={src} height={25} width={25} preview={false} />;
  };

  useEffect(() => {
    const currentPathSplit = currentPath.split("/");
    const currentPathLastIndex = currentPathSplit?.length - 1;

    const type = currentPathSplit[currentPathLastIndex];

    if (type !== INPUT && type !== OUTPUT) {
      return;
    }

    setConnectorType(type);

    const endpointType = CONNECTOR_TYPE_MAP[type]?.toUpperCase();

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow-endpoint/?workflow=${id}&endpoint_type=${endpointType}`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const endpoints = res?.data;
        if (endpoints?.length === 0) {
          setSelectedItem("");
          setListOfItems([]);
          return;
        }
        const menuItems = endpoints.map((item) =>
          getItem(
            item?.connector_name,
            item?.id,
            sourceIcon(item?.connector_icon)
          )
        );
        const firstId = endpoints[0].id.toString();
        setSelectedItem(firstId);
        setListOfItems(menuItems);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setReloadList(false);
      });
  }, [currentPath, reloadList]);

  const getItem = (label, key, icon, children, type) => {
    return {
      key,
      icon,
      children,
      label,
      type,
    };
  };

  const handleOpenModal = () => {
    setOpenModal(true);
  };

  const handleDelete = () => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow-endpoint/${selectedItem}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then(() => {
        setReloadList(true);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const addNewItem = (newItem, isEdit) => {
    let items = [...listOfItems];
    if (isEdit) {
      items = [...listOfItems].map((item) => {
        if (item?.key !== newItem?.id) {
          return item;
        }
        item["label"] = newItem?.connector_name;
        return item;
      });
    } else {
      const itemToAdd = getItem(
        newItem?.connector_name,
        newItem?.id,
        sourceIcon(newItem?.icon)
      );
      items.push(itemToAdd);
    }
    setListOfItems(items);

    setSelectedItem(newItem?.id);
  };

  return (
    <>
      {connectorType?.length > 0 && (
        <>
          <Row className="input-layout">
            <Col className="input-sidebar" span={4}>
              <Sidebar
                selectedItem={selectedItem}
                setSelectedItem={setSelectedItem}
                listOfItems={listOfItems}
                handleOpenModal={handleOpenModal}
                btnText={`Data ${CONNECTOR_TYPE_MAP[connectorType]}`}
              />
            </Col>
            <Col className="input-main" span={20}>
              <ManageFiles
                selectedItem={selectedItem}
                listOfitems={listOfItems}
                setEditItemId={setEditItemId}
                handleDelete={handleDelete}
              />
            </Col>
          </Row>
          <AddSourceModal
            open={openModal}
            setOpen={setOpenModal}
            type={connectorType}
            addNewItem={addNewItem}
            editItemId={editItemId}
            setEditItemId={setEditItemId}
          />
        </>
      )}
    </>
  );
}

export { InputOutput };

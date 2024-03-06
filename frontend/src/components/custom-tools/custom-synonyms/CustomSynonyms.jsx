import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Input, Select, Space, Table, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { handleException } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import "./CustomSynonyms.css";

const columns = [
  {
    title: "Word",
    dataIndex: "word",
    key: "word",
    width: 200,
  },
  {
    title: "Synonyms",
    dataIndex: "synonyms",
    key: "synonyms",
  },
  {
    title: "",
    dataIndex: "delete",
    key: "delete",
    width: 30,
  },
];

function CustomSynonyms({ setOpen }) {
  const [synonyms, setSynonyms] = useState([]);
  const [rows, setRows] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const { sessionDetails } = useSessionStore();
  const { details, updateCustomTool } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();

  useEffect(() => {
    const promptGrammar = details?.prompt_grammer;
    if (!promptGrammar || Object.keys(promptGrammar).length === 0) {
      setSynonyms([]);
      return;
    }

    const updatedSynonyms = Object.keys(promptGrammar).map((word, index) => {
      const value = promptGrammar[word];
      return {
        key: index,
        word,
        synonyms: value,
      };
    });

    setSynonyms(updatedSynonyms);
  }, [details]);

  useEffect(() => {
    if (!synonyms || synonyms.length === 0) {
      setRows([]);
      return;
    }

    const data = [...synonyms].map((item, index) => {
      const word = item?.word;
      const listOfSynonyms = item?.synonyms || [];
      return {
        key: index,
        word: (
          <Input
            value={word}
            variant="borderless"
            onChange={(event) =>
              handleChange(index, "word", event.target.value)
            }
          />
        ),
        synonyms: (
          <Select
            mode="tags"
            placeholder="Please select"
            value={listOfSynonyms}
            className="cus-syn-select"
            variant="borderless"
            onChange={(value) => handleChange(index, "synonyms", value)}
          />
        ),
        delete: (
          <ConfirmModal
            handleConfirm={() => handleDelete(index)}
            content="The word, along with its corresponding synonyms, will be permanently deleted."
          >
            <Button size="small" type="text">
              <DeleteOutlined className="cus-syn-del" />
            </Button>
          </ConfirmModal>
        ),
      };
    });

    setRows(data);
  }, [synonyms]);

  const handleChange = (index, propertyName, value) => {
    const updatedSynonyms = [...synonyms];
    updatedSynonyms[index][propertyName] = value;
    setSynonyms(updatedSynonyms);
  };

  const handleAddRow = () => {
    const length = synonyms.length || 0;
    const data = {
      key: length,
      word: "",
      synonyms: [],
    };
    const updatedSynonyms = [...synonyms];
    updatedSynonyms.push(data);
    setSynonyms(updatedSynonyms);
  };

  const handleDelete = (key) => {
    const updatedSynonyms = [...synonyms].filter((item) => item?.key !== key);
    setSynonyms(updatedSynonyms);
  };

  function isEmpty(obj) {
    if (typeof obj !== "object" || obj === null) {
      return true;
    }
    return Object.values(obj).every(
      (arr) => Array.isArray(arr) && arr.length === 0
    );
  }

  const handleSave = () => {
    const promptGrammar = {};
    [...synonyms].forEach((item) => {
      promptGrammar[item?.word] = item?.synonyms || [];
    });
    if (promptGrammar && !isEmpty(promptGrammar)) {
      const body = {
        prompt_grammer: promptGrammar,
      };
      const requestOptions = {
        method: "PATCH",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${details?.tool_id}/`,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: body,
      };

      setIsLoading(true);
      axiosPrivate(requestOptions)
        .then((res) => {
          const grammar = res?.data?.prompt_grammer;
          const updatedDetails = { ...details };
          updatedDetails["prompt_grammer"] = grammar;
          updateCustomTool(updatedDetails);
          setAlertDetails({
            type: "success",
            content: "Saved synonyms successfully",
          });
        })
        .catch((err) => {
          setAlertDetails(handleException(err, "Failed to update"));
        })
        .finally(() => {
          setIsLoading(false);
        });
    } else {
      setAlertDetails({
        type: "warning",
        content: "Please add synonyms to save",
      });
    }
  };

  return (
    <div>
      <div className="pre-post-amble-body">
        <SpaceWrapper>
          <div>
            <Typography.Text className="add-cus-tool-header">
              Custom Synonyms
            </Typography.Text>
          </div>
          <div>
            <Table
              columns={columns}
              dataSource={rows}
              size="small"
              bordered
              pagination={{ position: [] }}
            />
          </div>
          <div>
            <CustomButton
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleAddRow}
            >
              Rows
            </CustomButton>
          </div>
        </SpaceWrapper>
      </div>
      <div className="pre-post-amble-footer display-flex-right">
        <Space>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <CustomButton type="primary" onClick={handleSave} loading={isLoading}>
            Save
          </CustomButton>
        </Space>
      </div>
    </div>
  );
}

CustomSynonyms.propTypes = {
  setOpen: PropTypes.func.isRequired,
};

export { CustomSynonyms };

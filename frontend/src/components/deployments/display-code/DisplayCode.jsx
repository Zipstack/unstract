import { CheckCircleOutlined, CopyOutlined } from "@ant-design/icons";
import { Modal, Select, Tabs, Tooltip } from "antd";
import Handlebars from "handlebars";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import CodeSnippet from "./CodeSnippet.jsx";
import "./DisplayCode.css";

const DisplayCode = ({ isDialogOpen, setDialogOpen, url }) => {
  const [copied, setCopied] = useState(false);
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState("");
  const [activeTabKey, setActiveTabKey] = useState("POST");
  const params =
    "?execution_id=REPLACE_WITH_EXECUTION_ID&include_metadata=False";

  const handleCloseDialog = () => {
    setDialogOpen(false);
  };

  const generateCode = () => {
    if (language === "python") {
      generatePythonCode();
    } else if (language === "bash") {
      generateCurlCode();
    } else if (language === "javascript") {
      generateJavascriptCode();
    } else {
      setCode("");
    }
  };

  const trimIndent = (text) => {
    return text
      .split("\n")
      .map((line) => line.trim())
      .join("\n");
  };

  const generatePythonCode = () => {
    let code = `import requests
      {{#if isPost}}
        api_url = '{{url}}'
        headers = {
          'Authorization': 'Bearer REPLACE_WITH_API_KEY'
        }
        payload = {'timeout': 300, 'include_metadata': False}
        filepath = '/path/to/file'
        files=[('files',('file',open(filepath,'rb'),'application/octet-stream'))]
        response = requests.request("POST", api_url, headers=headers, data=payload, files=files)
      {{else}}
        api_url = '{{url}}{{{params}}}'
        headers = {
          'Authorization': 'Bearer REPLACE_WITH_API_KEY'
        }
        response = requests.request("GET", api_url, headers=headers)
      {{/if}}
      print('Response:', response.json())
    `;
    code = trimIndent(code);
    const template = Handlebars.compile(code);

    const pythonCode = template({
      url,
      params,
      isPost: activeTabKey === "POST",
    });
    setCode(pythonCode);
  };

  const generateCurlCode = () => {
    let code = `{{#if isPost}}
    curl --request POST --location '{{url}}' \\
    --header 'Authorization: Bearer REPLACE_WITH_API_KEY' \\
    --form 'files=@"{{pathToFile}}"' \\
    --form 'timeout=300' \\
    --form 'include_metadata=false'
    {{else}}
    curl --location '{{url}}{{{params}}}' \\
    --header 'Authorization: Bearer REPLACE_WITH_API_KEY'
    {{/if}}
  `;
    code = trimIndent(code);
    const template = Handlebars.compile(code);
    const curlCode = template({
      url,
      params,
      isPost: activeTabKey === "POST",
      pathToFile: "/path/to/file",
    });
    setCode(curlCode);
  };

  const generateJavascriptCode = () => {
    let code = `var myHeaders = new Headers();
    myHeaders.append("Authorization", "Bearer REPLACE_WITH_API_KEY");
    {{#if isPost}}
    var formdata = new FormData();
    formdata.append("files", fileInput.files[0], "file");
    formdata.append("timeout", "300");
    formdata.append("include_metadata", "false");
    var requestOptions = { method: 'POST', body: formdata, redirect: 'follow', headers: myHeaders };
    fetch("{{url}}", requestOptions)
    {{else}}
    var requestOptions = { method: 'GET', redirect: 'follow', headers: myHeaders};
    fetch("{{url}}{{{params}}}", requestOptions)
    {{/if}}
    .then(response => response.text())
    .then(result => console.log(result))
    .catch(error => console.log('error', error));
    `;
    code = trimIndent(code);
    const template = Handlebars.compile(code);

    const jsCode = template({ url, params, isPost: activeTabKey === "POST" });
    setCode(jsCode);
  };

  const handleCopyClick = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleTabKey = (key) => {
    setActiveTabKey(key.toString());
  };

  const onChangeHandler = (value) => {
    setLanguage(value);
  };

  const TAB_ITEMS = [
    {
      key: "POST",
      label: "POST Document",
      children: <CodeSnippet code={code} />,
    },
    {
      key: "GET",
      label: "GET Status",
      children: <CodeSnippet code={code} />,
    },
  ];

  const LANGUAGE_OPTIONS = [
    {
      value: "python",
      label: "Python",
    },
    {
      value: "bash",
      label: "cURL",
    },
    {
      value: "javascript",
      label: "JavaScript",
    },
  ];

  useEffect(() => {
    generateCode();
  }, [url, language, activeTabKey]);

  return (
    <Modal
      title="Code Snippets"
      centered
      maskClosable={false}
      open={isDialogOpen}
      onCancel={handleCloseDialog}
      width={700}
      footer={null}
    >
      <Tabs
        defaultActiveKey="1"
        tabBarExtraContent={
          <div className="codeActions">
            <Select
              className="codeLanguage"
              width={300}
              onChange={(value) => onChangeHandler(value)}
              name="language"
              value={language}
              options={LANGUAGE_OPTIONS}
            />
            <button className="copyCodeBtn" onClick={handleCopyClick}>
              {copied ? (
                <Tooltip title="Copied">
                  <CheckCircleOutlined />
                </Tooltip>
              ) : (
                <Tooltip title="Copy snippet">
                  <CopyOutlined />
                </Tooltip>
              )}
            </button>
          </div>
        }
        onChange={handleTabKey}
        items={TAB_ITEMS}
        moreIcon={<></>}
      />
    </Modal>
  );
};

DisplayCode.propTypes = {
  isDialogOpen: PropTypes.bool.isRequired,
  setDialogOpen: PropTypes.func.isRequired,
  url: PropTypes.string.isRequired,
};

export { DisplayCode };

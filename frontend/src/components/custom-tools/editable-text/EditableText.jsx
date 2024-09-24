import { Input } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import PropTypes from "prop-types";
import debounce from "lodash/debounce";

import "./EditableText.css";
import { useCustomToolStore } from "../../../store/custom-tool-store";
function EditableText({
  isEditing,
  setIsEditing,
  text,
  setText,
  promptId,
  defaultText,
  handleChange,
  isTextarea,
  placeHolder,
}) {
  const name = isTextarea ? "prompt" : "prompt_key";
  const [triggerHandleChange, setTriggerHandleChange] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const divRef = useRef(null);
  const {
    disableLlmOrDocChange,
    indexDocs,
    selectedDoc,
    isSinglePassExtractLoading,
    isPublicSource,
  } = useCustomToolStore();

  useEffect(() => {
    setText(defaultText);
  }, [defaultText]);

  useEffect(() => {
    // Attach the event listener when the component mounts
    document.addEventListener("click", handleClickOutside);

    // Clean up the event listener when the component unmounts
    return () => {
      document.removeEventListener("click", handleClickOutside);
    };
  }, []);

  const handleBlur = () => {
    setIsEditing(false);
  };

  const handleTextChange = (event) => {
    const value = event.target.value;
    setText(value);
    onSearchDebounce(event);
  };

  const onSearchDebounce = useCallback(
    debounce((event) => {
      setTriggerHandleChange(true);
    }, 1000),
    []
  );

  useEffect(() => {
    if (!triggerHandleChange) {
      return;
    }
    handleChange(text, promptId, name, true, false);
    setTriggerHandleChange(false);
  }, [triggerHandleChange]);

  const handleClickOutside = (event) => {
    if (divRef.current && !divRef.current.contains(event.target)) {
      // Clicked outside the div
      setIsEditing(false);
    }
  };

  if (isTextarea) {
    return (
      <Input.TextArea
        className="font-size-12 width-100"
        value={text}
        onChange={handleTextChange}
        placeholder={placeHolder}
        name={name}
        size="small"
        style={{ backgroundColor: "transparent" }}
        variant={`${!isEditing && !isHovered ? "borderless" : "outlined"}`}
        autoSize={true}
        onMouseOver={() => setIsHovered(true)}
        onMouseOut={() => setIsHovered(false)}
        onBlur={handleBlur}
        onClick={() => setIsEditing(true)}
        disabled={
          disableLlmOrDocChange.includes(promptId) ||
          isSinglePassExtractLoading ||
          isPublicSource
        }
      />
    );
  }

  return (
    <Input
      className="width-100 input-header-text"
      value={text}
      onChange={handleTextChange}
      placeholder="Enter Key"
      name={name}
      size="small"
      style={{ backgroundColor: "transparent" }}
      variant={`${!isEditing && !isHovered ? "borderless" : "outlined"}`}
      autoSize={true}
      onMouseOver={() => setIsHovered(true)}
      onMouseOut={() => setIsHovered(false)}
      onBlur={handleBlur}
      onClick={() => setIsEditing(true)}
      disabled={
        disableLlmOrDocChange.includes(promptId) ||
        indexDocs.includes(selectedDoc?.document_id) ||
        isSinglePassExtractLoading ||
        isPublicSource
      }
    />
  );
}

EditableText.propTypes = {
  isEditing: PropTypes.bool.isRequired,
  setIsEditing: PropTypes.func.isRequired,
  text: PropTypes.string,
  setText: PropTypes.func.isRequired,
  promptId: PropTypes.string,
  defaultText: PropTypes.string,
  handleChange: PropTypes.func.isRequired,
  isTextarea: PropTypes.bool,
  placeHolder: PropTypes.string,
};

export { EditableText };

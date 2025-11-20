import PropTypes from "prop-types";
import { useRef, useImperativeHandle, forwardRef } from "react";
import Editor from "@monaco-editor/react";

const MonacoEditor = forwardRef(
  (
    { value, onChange, language = "json", readOnly = false, height = "600px" },
    ref
  ) => {
    const editorRef = useRef(null);

    // Expose find method via ref
    useImperativeHandle(ref, () => ({
      find: (query) => {
        if (editorRef.current) {
          const editor = editorRef.current;
          editor.focus();
          const findController = editor.getContribution(
            "editor.contrib.findController"
          );
          if (findController) {
            findController.start({
              searchString: query,
              replaceString: "",
              isRegex: false,
              matchCase: false,
              wholeWord: false,
              isCaseSensitive: false,
              preserveCase: false,
            });

            // Focus the find widget's input field after a short delay
            setTimeout(() => {
              const findWidget = editor
                .getDomNode()
                ?.querySelector(".find-widget");
              if (findWidget) {
                const searchInput = findWidget.querySelector(
                  ".monaco-findInput textarea.input"
                );
                if (searchInput) {
                  searchInput.focus();
                  searchInput.select();
                }
              }
            }, 50);
          }
        }
      },
    }));

    const handleEditorDidMount = (editor) => {
      editorRef.current = editor;

      // Configure editor options
      editor.updateOptions({
        readOnly,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: "on",
        renderWhitespace: "selection",
        automaticLayout: true,
        wordWrap: "on",
        wrappingStrategy: "advanced",
      });

      // Format document on mount for JSON
      if (language === "json" && value && !readOnly) {
        try {
          JSON.parse(value);
          setTimeout(() => {
            editor.getAction("editor.action.formatDocument")?.run();
          }, 100);
        } catch (e) {
          // Invalid JSON, don't format
        }
      }
    };

    const handleEditorChange = (newValue) => {
      if (onChange && newValue !== undefined) {
        onChange(newValue);
      }
    };

    return (
      <div
        style={{
          border: "1px solid #d9d9d9",
          borderRadius: "4px",
          overflow: "hidden",
          height: "100%",
          width: "100%",
        }}
      >
        <Editor
          height={height}
          language={language}
          value={value}
          onChange={handleEditorChange}
          onMount={handleEditorDidMount}
          theme="vs-light"
          options={{
            readOnly,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 13,
            lineNumbers: "on",
            renderWhitespace: "selection",
            automaticLayout: true,
            wordWrap: "on",
            wrappingStrategy: "advanced",
          }}
        />
      </div>
    );
  }
);

MonacoEditor.displayName = "MonacoEditor";

MonacoEditor.propTypes = {
  value: PropTypes.string,
  onChange: PropTypes.func,
  language: PropTypes.string,
  readOnly: PropTypes.bool,
  height: PropTypes.string,
};

export default MonacoEditor;

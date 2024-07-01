import { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";

const useResize = ({ minHeight }) => {
  const [isResizing, setIsResizing] = useState(false);
  const [height, setHeight] = useState(minHeight);

  const enableResize = useCallback(() => {
    setIsResizing(true);
  }, [setIsResizing]);

  const disableResize = useCallback(() => {
    setIsResizing(false);
  }, [setIsResizing]);

  const resize = useCallback(
    (e) => {
      if (isResizing) {
        const newHeight = window.innerHeight - e.clientY;
        if (newHeight >= minHeight) {
          setHeight(newHeight);
        }
      }
    },
    [minHeight, isResizing, setHeight]
  );

  useEffect(() => {
    const handleMouseMove = (e) => resize(e);
    const handleMouseUp = () => disableResize();

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [disableResize, resize]);

  return { height, enableResize, setHeight };
};

useResize.propTypes = {
  minHeight: PropTypes.number.isRequired,
};

export { useResize };

import PropTypes from "prop-types";
import * as React from "react";
import { Button } from "@/components/ui/antd-button";

import "./CustomButton.css";

/**
 * forwardRef is load-bearing, not decoration. CustomButton is used as the
 * child of `<Dropdown>`, whose Radix trigger renders with `asChild` and needs
 * a ref to attach its handlers. As a plain function component the ref was
 * dropped, the trigger was inert, and clicking Export in Prompt Studio did
 * nothing at all — no menu, no network request.
 */
const CustomButton = React.forwardRef(function CustomButton(props, ref) {
  const { type } = props;

  return (
    <Button
      ref={ref}
      className={type === "primary" ? "custom-button-primary" : ""}
      {...props}
    />
  );
});

CustomButton.propTypes = {
  type: PropTypes.string,
  disabled: PropTypes.bool,
};

export { CustomButton };

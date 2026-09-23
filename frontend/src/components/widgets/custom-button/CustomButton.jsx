import PropTypes from "prop-types";
import * as React from "react";
import { Button } from "@/components/ui/shims/antd-button";

/**
 * forwardRef is load-bearing, not decoration. CustomButton is used as the
 * child of `<Dropdown>`, whose Radix trigger renders with `asChild` and needs
 * a ref to attach its handlers. As a plain function component the ref was
 * dropped, the trigger was inert, and clicking Export in Prompt Studio did
 * nothing at all — no menu, no network request.
 */
/*
 * CustomButton.css used to repaint `type="primary"` navy (#092c4c) on top of
 * the Button shim's output. That override is gone, along with the file: the
 * shim already maps antd `type="primary"` to the shadcn `default` variant,
 * i.e. `bg-primary` = Midnight Bloom violet. Keeping a second definition of
 * "primary" meant the 24 CustomButton call-sites rendered a different colour
 * from every plain `<Button type="primary">` elsewhere in the app.
 *
 * CustomButton now exists purely for the forwardRef below.
 */
const CustomButton = React.forwardRef(function CustomButton(props, ref) {
  return <Button ref={ref} {...props} />;
});

CustomButton.propTypes = {
  type: PropTypes.string,
  disabled: PropTypes.bool,
};

export { CustomButton };

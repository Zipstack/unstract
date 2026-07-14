import { Typography } from "antd";
import PropTypes from "prop-types";
import { Component } from "react";

const { Text } = Typography;

// Shallow element-wise compare; resetKeys are typically fresh arrays each
// render (e.g. [location.pathname]), so a reference check would never match.
function resetKeysChanged(prev = [], next = []) {
  return prev.length !== next.length || prev.some((v, i) => v !== next[i]);
}

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {};
  }

  componentDidCatch(error, errorInfo) {
    console.error("Error ", error);
    this.props.onError({ error, errorInfo });
    this.setState({ error });
  }

  componentDidUpdate(prevProps) {
    // Once a value in resetKeys changes (e.g. the user navigated), clear the
    // error so the boundary re-renders its children — recovery without a
    // full page reload.
    if (
      this.state.error &&
      resetKeysChanged(prevProps.resetKeys, this.props.resetKeys)
    ) {
      this.setState({ error: undefined });
    }
  }

  render() {
    return this.state.error
      ? this.props.fallbackComponent
      : this.props.children;
  }
}

ErrorBoundary.propTypes = {
  /**
   * Children component wrapped by the error boundary
   */
  children: PropTypes.any,
  /**
   * Event handler when error occurs
   */
  onError: PropTypes.func,
  /**
   * Custom component to render when error occurs,
   * By default, it shows "There was an error" message
   */
  fallbackComponent: PropTypes.any,
  /**
   * When any value in this array changes while in the error state, the
   * boundary resets and re-renders its children (e.g. [location.pathname]
   * so navigation recovers without a reload).
   */
  resetKeys: PropTypes.array,
};

ErrorBoundary.defaultProps = {
  onError: () => {
    // No-op default error handler
  },
  fallbackComponent: <Text type="danger">There was an error</Text>,
};

export { ErrorBoundary };

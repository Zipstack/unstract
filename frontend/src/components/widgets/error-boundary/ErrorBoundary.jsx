import { Typography } from "antd";
import PropTypes from "prop-types";
import { Component } from "react";

const { Text } = Typography;

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
};

ErrorBoundary.defaultProps = {
  onError: () => {},
  fallbackComponent: <Text type="danger">There was an error</Text>,
};

export { ErrorBoundary };

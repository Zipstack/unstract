import PropTypes from "prop-types";
import { lazy, Suspense, useMemo } from "react";

function LazyLoader(props) {
  const { component, componentName, loader, innerRef, ...rest } = props;

  const LazyLoadedComponent = useMemo(function memoizedComponent() {
    return lazy(() =>
      component().then((module) => {
        return { default: module[componentName || "default"] };
      }),
    );
  }, []);

  return (
    <Suspense fallback={loader || null}>
      <LazyLoadedComponent {...rest} ref={innerRef} />
    </Suspense>
  );
}

LazyLoader.propTypes = {
  component: PropTypes.any,
  componentName: PropTypes.string,
  loader: PropTypes.node,
  error: PropTypes.node,
  innerRef: PropTypes.any,
};

export { LazyLoader };

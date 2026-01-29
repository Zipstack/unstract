import { Card, Col, Row, Skeleton } from "antd";
import PropTypes from "prop-types";

/**
 * Loading skeleton that matches the card grid layout
 *
 * @param {Object} props - Component props
 * @param {Object} props.gridConfig - Grid configuration for responsive columns
 * @param {number} props.count - Number of skeleton cards to display
 * @return {JSX.Element} The rendered loading skeleton grid
 */
function LoadingSkeleton({ gridConfig, count = 6 }) {
  const defaultColumns = {
    xs: 24,
    sm: 24,
    md: 12,
    lg: 12,
    xl: 8,
    xxl: 8,
  };

  const columns = gridConfig?.columns || defaultColumns;
  const gutter = gridConfig?.gutter || [16, 16];

  return (
    <Row gutter={gutter} className="card-skeleton-row">
      {Array.from({ length: count }).map((_, index) => (
        <Col
          key={index}
          xs={columns.xs}
          sm={columns.sm}
          md={columns.md}
          lg={columns.lg}
          xl={columns.xl}
          xxl={columns.xxl}
        >
          <Card className="card-skeleton-item">
            <Skeleton active paragraph={{ rows: 3 }} />
          </Card>
        </Col>
      ))}
    </Row>
  );
}

LoadingSkeleton.propTypes = {
  gridConfig: PropTypes.shape({
    gutter: PropTypes.arrayOf(PropTypes.number),
    columns: PropTypes.shape({
      xs: PropTypes.number,
      sm: PropTypes.number,
      md: PropTypes.number,
      lg: PropTypes.number,
      xl: PropTypes.number,
      xxl: PropTypes.number,
    }),
  }),
  count: PropTypes.number,
};

export { LoadingSkeleton };

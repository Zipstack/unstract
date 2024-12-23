import { Helmet } from "react-helmet-async";
import PropTypes from "prop-types";

function PageTitle({ title }) {
  return (
    <Helmet>
      <title>{title ? `${title} - Unstract` : "Unstract"}</title>
    </Helmet>
  );
}

PageTitle.propTypes = {
  title: PropTypes.string,
};

export { PageTitle };

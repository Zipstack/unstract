import { Col, Row, Tag } from "antd";
import PropTypes from "prop-types";
import "./ProfileInfoBar.css";

const ProfileInfoBar = ({ profiles, profileId }) => {
  const profile = profiles?.find((p) => p?.profile_id === profileId);

  if (!profile) {
    return <p>Profile not found</p>;
  }

  return (
    <Row className="profile-info-bar">
      <Col>
        <Tag>
          <strong>Profile Name:</strong> {profile?.profile_name}
        </Tag>
      </Col>
      <Col>
        <Tag>
          <strong>Chunk Size:</strong> {profile?.chunk_size}
        </Tag>
      </Col>
      <Col>
        <Tag>
          <strong>Vector Store:</strong> {profile?.vector_store}
        </Tag>
      </Col>
      <Col>
        <Tag>
          <strong>Embedding Model:</strong> {profile?.embedding_model}
        </Tag>
      </Col>
      <Col>
        <Tag>
          <strong>LLM:</strong> {profile?.llm}
        </Tag>
      </Col>
      <Col>
        <Tag>
          <strong>X2Text:</strong> {profile?.x2text}
        </Tag>
      </Col>
      <Col>
        <Tag>
          <strong>Reindex:</strong> {profile?.reindex ? "Yes" : "No"}
        </Tag>
      </Col>
    </Row>
  );
};

ProfileInfoBar.propTypes = {
  profiles: PropTypes.array,
  profileId: PropTypes.string,
};

export { ProfileInfoBar };

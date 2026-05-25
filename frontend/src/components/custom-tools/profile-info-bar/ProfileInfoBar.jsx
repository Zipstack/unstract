import { Tag } from "antd";
import PropTypes from "prop-types";
import "./ProfileInfoBar.css";

const ProfileInfoBar = ({ profiles, profileId }) => {
  const profile = profiles?.find((p) => p?.profile_id === profileId);

  if (!profile) {
    return <p>Profile not found</p>;
  }

  return (
    <div className="profile-info-bar">
      <Tag>
        <strong>Profile Name:</strong> {profile?.profile_name}
      </Tag>
      <Tag>
        <strong>Chunk Size:</strong> {profile?.chunk_size}
      </Tag>
      <Tag>
        <strong>Vector Store:</strong> {profile?.vector_store}
      </Tag>
      <Tag>
        <strong>Embedding Model:</strong> {profile?.embedding_model}
      </Tag>
      <Tag>
        <strong>LLM:</strong> {profile?.llm}
      </Tag>
      <Tag>
        <strong>X2Text:</strong> {profile?.x2text}
      </Tag>
      <Tag>
        <strong>Reindex:</strong> {profile?.reindex ? "Yes" : "No"}
      </Tag>
    </div>
  );
};

ProfileInfoBar.propTypes = {
  profiles: PropTypes.array,
  profileId: PropTypes.string,
};

export { ProfileInfoBar };

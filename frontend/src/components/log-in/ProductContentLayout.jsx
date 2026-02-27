import { Typography } from "antd";

// Load assets from plugins directory (available in cloud, gitignored in OSS)
async function loadAsset(path) {
  try {
    const mod = await import(/* @vite-ignore */ path);
    return mod.default;
  } catch {
    return "";
  }
}

// LLMWhisperer assets
const anthropicLogo = await loadAsset(
  "../../plugins/assets/llmWhisperer/Anthropic.svg",
);
const azureGptLogo = await loadAsset(
  "../../plugins/assets/llmWhisperer/Azure GPT.png",
);
const llmG2Badge = await loadAsset(
  "../../plugins/assets/llmWhisperer/G2-Badge.png",
);
const gdprBadge = await loadAsset(
  "../../plugins/assets/llmWhisperer/GDPR.webp",
);
const gregCrisciPhoto = await loadAsset(
  "../../plugins/assets/llmWhisperer/Greg Crisci.jpeg",
);
const hipaaBadge = await loadAsset(
  "../../plugins/assets/llmWhisperer/HIPAA-1.png.webp",
);
const isoBadge = await loadAsset(
  "../../plugins/assets/llmWhisperer/ISO-27001.png",
);
const openAiLogo = await loadAsset(
  "../../plugins/assets/llmWhisperer/OpenAI-icon.svg",
);
const quoteIcon = await loadAsset(
  "../../plugins/assets/llmWhisperer/quote-icon.svg",
);
const soc2Badge = await loadAsset(
  "../../plugins/assets/llmWhisperer/SOC2-Type-II.png",
);
const statIconAccuracy = await loadAsset(
  "../../plugins/assets/llmWhisperer/stat-icon-accuracy.svg",
);
const statIconManual = await loadAsset(
  "../../plugins/assets/llmWhisperer/stat-icon-manual.svg",
);
const statIconTouchpoints = await loadAsset(
  "../../plugins/assets/llmWhisperer/stat-icon-touchpoints.svg",
);
const vertexAiLogo = await loadAsset(
  "../../plugins/assets/llmWhisperer/Vertex AI.svg",
);

// Unstract assets
const christopherVarnerPhoto = await loadAsset(
  "../../plugins/assets/unstract/Christopher Varner.jpeg",
);
const cybersoftLogo = await loadAsset(
  "../../plugins/assets/unstract/cybersoft.png",
);
const endpointClinicalLogo = await loadAsset(
  "../../plugins/assets/unstract/endpoint-clinical.svg",
);
const unstractG2BadgeNew = await loadAsset(
  "../../plugins/assets/unstract/G2-Badge-new.png",
);
const medaxionLogo = await loadAsset(
  "../../plugins/assets/unstract/medaxion.svg",
);
const moodysLogo = await loadAsset("../../plugins/assets/unstract/moodys.png");
const unstractQuoteIcon = await loadAsset(
  "../../plugins/assets/unstract/quote-icon.svg",
);
const unstractStatIconAccuracy = await loadAsset(
  "../../plugins/assets/unstract/stat-icon-accuracy.svg",
);
const unstractStatIconEfficiency = await loadAsset(
  "../../plugins/assets/unstract/stat-icon-efficiency.svg",
);
const unstractStatIconStp = await loadAsset(
  "../../plugins/assets/unstract/stat-icon-stp.svg",
);

const COMPLIANCE_BADGES = [
  { name: "SOC2 Type II", logo: soc2Badge },
  { name: "GDPR", logo: gdprBadge },
  { name: "ISO", logo: isoBadge },
  { name: "HIPAA", logo: hipaaBadge },
  { name: "G2 Users Love Us", logo: unstractG2BadgeNew },
];

const TRUSTED_LOGOS = [
  { name: "Moody's", logo: moodysLogo },
  { name: "Endpoint Clinical", logo: endpointClinicalLogo },
  { name: "Cybersoft", logo: cybersoftLogo },
  { name: "Medaxion", logo: medaxionLogo },
];

const LLM_PROVIDERS = [
  { name: "Anthropic", logo: anthropicLogo },
  { name: "Azure GPT", logo: azureGptLogo },
  { name: "OpenAI", logo: openAiLogo },
  { name: "Vertex AI", logo: vertexAiLogo },
];

function ProductContentLayout() {
  return (
    <div className="default-light-content">
      <Typography.Title level={2} className="default-light-headline">
        <span className="default-light-headline-dark">
          {"Parse, Structure and Automate "}
        </span>
        <span className="default-light-headline-accent">
          Document Extraction
        </span>
      </Typography.Title>

      <div className="default-light-badges-row">
        {COMPLIANCE_BADGES.map((badge) => (
          <div key={badge.name} className="default-light-compliance-badge">
            <img
              src={badge.logo}
              alt={badge.name}
              className="default-light-compliance-logo"
            />
          </div>
        ))}
      </div>

      <div className="default-light-product-card">
        <Typography.Text className="default-light-card-title">
          Unstract
        </Typography.Text>
        <div className="default-light-card-body">
          <Typography.Paragraph className="default-light-card-text">
            Unstract automates document workflows using AI, eliminating manual
            data entry from complex, unstructured documents — at enterprise
            scale.
          </Typography.Paragraph>
          <div className="default-light-card-divider" />
          <div className="default-light-card-footer">
            <Typography.Text className="default-light-card-footer-label">
              Trusted by Enterprises
            </Typography.Text>
            <div className="default-light-card-logos">
              {TRUSTED_LOGOS.map((company) => (
                <img
                  key={company.name}
                  src={company.logo}
                  alt={company.name}
                  className="default-light-card-logo"
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="default-light-product-card">
        <Typography.Text className="default-light-card-title">
          LLMWhisperer
        </Typography.Text>
        <div className="default-light-card-body">
          <Typography.Paragraph className="default-light-card-text">
            LLMWhisperer parses text from documents and makes it ready for LLM
            consumption.
          </Typography.Paragraph>
          <div className="default-light-card-divider" />
          <div className="default-light-card-footer">
            <Typography.Text className="default-light-card-footer-label">
              Plays well with leading LLMs
            </Typography.Text>
            <div className="default-light-card-logos">
              {LLM_PROVIDERS.map((provider) => (
                <img
                  key={provider.name}
                  src={provider.logo}
                  alt={provider.name}
                  className="default-light-card-provider-logo"
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const LLM_STATS = [
  {
    value: "99.9%",
    label: "Extraction\nAccuracy",
    icon: statIconAccuracy,
    gradient: "linear-gradient(-90deg, #00a6ed, #75deec)",
  },
  {
    value: "90%",
    label: "Reduced\nManual Work",
    icon: statIconManual,
    gradient: "linear-gradient(109deg, #33b8f1, #ff7d95)",
  },
  {
    value: "80%",
    label: "Lesser Human\nTouchpoints",
    icon: statIconTouchpoints,
    gradient: "linear-gradient(109deg, #ffde8e, #ff7d95)",
  },
];

const LLM_COMPLIANCE_BADGES = [
  { name: "SOC2 Type II", logo: soc2Badge },
  { name: "GDPR", logo: gdprBadge },
  { name: "ISO", logo: isoBadge },
  { name: "HIPAA", logo: hipaaBadge },
  { name: "G2 Users Love Us", logo: llmG2Badge },
];

function LlmWhispererContent() {
  return (
    <div className="llm-light-content">
      <Typography.Title level={2} className="llm-light-headline">
        <span className="llm-light-headline-dark">Make parsed text ready</span>
        <br />
        <span className="llm-light-headline-accent">for LLM extraction</span>
      </Typography.Title>

      <div className="llm-light-badges-row">
        {LLM_COMPLIANCE_BADGES.map((badge) => (
          <div key={badge.name} className="llm-light-compliance-badge">
            <img
              src={badge.logo}
              alt={badge.name}
              className="llm-light-compliance-logo"
            />
          </div>
        ))}
      </div>

      <div className="llm-light-stats-bar">
        {LLM_STATS.map((stat) => (
          <div key={stat.label} className="llm-light-stat-card">
            <div
              className="llm-light-stat-icon"
              style={{ background: stat.gradient }}
            >
              <img src={stat.icon} alt="" className="llm-light-stat-icon-img" />
            </div>
            <span className="llm-light-stat-value">{stat.value}</span>
            <span className="llm-light-stat-label">{stat.label}</span>
          </div>
        ))}
      </div>

      <div className="llm-light-testimonial">
        <div className="llm-light-testimonial-quote-row">
          <img
            src={quoteIcon}
            alt=""
            className="llm-light-testimonial-quote-icon"
          />
          <Typography.Paragraph className="llm-light-testimonial-text">
            &ldquo;The features like changing the quality type, bounding around
            tables are super helpful. When you compare the accuracy of the
            outputs of LLMWhisperer vs. others like PDF.co, the difference is
            night and day.&rdquo;
          </Typography.Paragraph>
        </div>
        <div className="llm-light-testimonial-author">
          <img
            src={gregCrisciPhoto}
            alt="Greg Crisci"
            className="llm-light-testimonial-avatar"
          />
          <div className="llm-light-testimonial-author-info">
            <Typography.Text strong className="llm-light-testimonial-name">
              Greg Crisci
            </Typography.Text>
            <Typography.Text className="llm-light-testimonial-role">
              Advisor
            </Typography.Text>
          </div>
        </div>
      </div>

      <div className="llm-light-providers-section">
        <div className="llm-light-providers-label-row">
          <span className="llm-light-providers-line" />
          <Typography.Text className="llm-light-providers-label">
            Plays well with leading LLMs
          </Typography.Text>
          <span className="llm-light-providers-line" />
        </div>
        <div className="llm-light-providers-logos">
          {LLM_PROVIDERS.map((provider) => (
            <div key={provider.name} className="llm-light-provider-badge">
              <img
                src={provider.logo}
                alt={provider.name}
                className="llm-light-provider-logo"
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const UNSTRACT_STATS_LIGHT = [
  {
    value: "20x",
    label: "Improvement in\nOperational Efficiency",
    icon: unstractStatIconEfficiency,
    gradient: "linear-gradient(-90deg, #00a6ed, #75deec)",
  },
  {
    value: "99.9%",
    label: "Extraction\nAccuracy",
    icon: unstractStatIconAccuracy,
    gradient: "linear-gradient(109deg, #33b8f1, #ff7d95)",
  },
  {
    value: "90%+",
    label: "Straight-Through\nProcessing",
    icon: unstractStatIconStp,
    gradient: "linear-gradient(109deg, #ffde8e, #ff7d95)",
  },
];

function UnstractContent() {
  return (
    <div className="unstract-light-content">
      <Typography.Title level={2} className="unstract-light-headline">
        <span className="unstract-light-headline-dark">
          Turn messy documents
        </span>
        <br />
        <span className="unstract-light-headline-accent">
          into structured data
        </span>
      </Typography.Title>

      <div className="unstract-light-badges-row">
        {COMPLIANCE_BADGES.map((badge) => (
          <div key={badge.name} className="unstract-light-compliance-badge">
            <img
              src={badge.logo}
              alt={badge.name}
              className="unstract-light-compliance-logo"
            />
          </div>
        ))}
      </div>

      <div className="unstract-light-stats-bar">
        {UNSTRACT_STATS_LIGHT.map((stat) => (
          <div key={stat.label} className="unstract-light-stat-card">
            <div
              className="unstract-light-stat-icon"
              style={{ background: stat.gradient }}
            >
              <img
                src={stat.icon}
                alt=""
                className="unstract-light-stat-icon-img"
              />
            </div>
            <span className="unstract-light-stat-value">{stat.value}</span>
            <span className="unstract-light-stat-label">{stat.label}</span>
          </div>
        ))}
      </div>

      <div className="unstract-light-testimonial">
        <div className="unstract-light-testimonial-quote-row">
          <img
            src={unstractQuoteIcon}
            alt=""
            className="unstract-light-testimonial-quote-icon"
          />
          <Typography.Paragraph className="unstract-light-testimonial-text">
            &ldquo;Unstract has cut down the time required to complete tasks
            that we have to do multiple times. It&apos;s reduced the manual
            review of many hundreds of pages of documents and summarizes key
            details for analysis.&rdquo;
          </Typography.Paragraph>
        </div>
        <div className="unstract-light-testimonial-author">
          <img
            src={christopherVarnerPhoto}
            alt="Christopher Varner"
            className="unstract-light-testimonial-avatar"
          />
          <div className="unstract-light-testimonial-author-info">
            <Typography.Text strong className="unstract-light-testimonial-name">
              Christopher Varner
            </Typography.Text>
            <Typography.Text className="unstract-light-testimonial-role">
              Senior Director, Solutions
            </Typography.Text>
            <Typography.Text className="unstract-light-testimonial-company">
              Endpoint Clinical
            </Typography.Text>
          </div>
        </div>
      </div>

      <div className="unstract-light-trusted-section">
        <div className="unstract-light-trusted-label-row">
          <span className="unstract-light-trusted-line" />
          <Typography.Text className="unstract-light-trusted-label">
            Trusted by Enterprises
          </Typography.Text>
          <span className="unstract-light-trusted-line" />
        </div>
        <div className="unstract-light-trusted-logos">
          {TRUSTED_LOGOS.map((company) => (
            <div key={company.name} className="unstract-light-trusted-badge">
              <img
                src={company.logo}
                alt={company.name}
                className="unstract-light-trusted-logo"
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export { ProductContentLayout, LlmWhispererContent, UnstractContent };

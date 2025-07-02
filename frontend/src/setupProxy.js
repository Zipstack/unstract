const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = (app) => {
  // Only set up proxy if REACT_APP_BACKEND_URL is provided
  if (
    process.env.REACT_APP_BACKEND_URL &&
    process.env.REACT_APP_BACKEND_URL.trim() !== ""
  ) {
    app.use(
      "/api/v1",
      createProxyMiddleware({
        target: process.env.REACT_APP_BACKEND_URL,
        changeOrigin: true,
      })
    );
  }
};

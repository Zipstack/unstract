const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = (app) => {
  app.use(
    "/api/v1",
    createProxyMiddleware({
      target: process.env.REACT_APP_BACKEND_URL,
      changeOrigin: true,
    })
  );
  app.use(
    "/public",
    createProxyMiddleware({
      target: process.env.REACT_APP_BACKEND_URL,
      changeOrigin: true,
    })
  );
  app.use(
    "/llmwhisperer",
    createProxyMiddleware({
      target: process.env.REACT_APP_WHISPERER_BACKEND_URL,
      changeOrigin: true,
    })
  );
};

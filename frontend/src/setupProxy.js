const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function setupProxy(app) {
  const explicitTarget = process.env.BACKEND_PROXY_TARGET;
  const target = explicitTarget;

  if (!target) {
    // fail-fast by design: proxy target must come from env
    return;
  }

  app.use(
    "/api",
    createProxyMiddleware({
      target,
      changeOrigin: true,
      ws: true,
      secure: false,
      xfwd: true,
      logLevel: "warn",
      pathRewrite: (path) => {
        if (path.startsWith("/api")) {
          return path;
        }
        return `/api${path}`;
      },
      onError(err, req, res) {
        if (!res.headersSent) {
          res.writeHead(502, { "Content-Type": "application/json" });
        }
        res.end(
          JSON.stringify({
            detail: "backend_proxy_unreachable",
            path: req?.url || "/api",
            message: err?.message || "proxy_error",
          }),
        );
      },
    }),
  );
};

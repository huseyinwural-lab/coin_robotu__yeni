const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const buildDir = path.join(__dirname, "..", "build");
const reportPath = path.join(buildDir, "perf-smoke-report.json");

const thresholdProfiles = {
  dev: {
    main_js_gzip_kb_max: 750,
    main_css_gzip_kb_max: 90,
  },
  stage: {
    main_js_gzip_kb_max: 650,
    main_css_gzip_kb_max: 70,
  },
  prod: {
    main_js_gzip_kb_max: 600,
    main_css_gzip_kb_max: 50,
  },
};

function bytesToKb(value) {
  return Number((value / 1024).toFixed(2));
}

function statWithGzip(filePath) {
  const rawBuffer = fs.readFileSync(filePath);
  const gzipBuffer = zlib.gzipSync(rawBuffer, { level: 9 });
  return {
    bytes: rawBuffer.length,
    kb: bytesToKb(rawBuffer.length),
    gzip_bytes: gzipBuffer.length,
    gzip_kb: bytesToKb(gzipBuffer.length),
  };
}

function main() {
  const manifestPath = path.join(buildDir, "asset-manifest.json");
  if (!fs.existsSync(manifestPath)) {
    throw new Error("asset-manifest.json bulunamadı. Önce yarn build çalıştırılmalı.");
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
  const files = manifest.files || {};
  const mainJsRel = files["main.js"];
  const mainCssRel = files["main.css"];

  const requestedProfile = String(process.env.PERF_SMOKE_PROFILE || "dev").toLowerCase();
  const thresholdProfile = thresholdProfiles[requestedProfile] ? requestedProfile : "dev";

  const report = {
    generated_at: new Date().toISOString(),
    status: "PASS",
    threshold_profile: thresholdProfile,
    checks: {
      build_exists: fs.existsSync(buildDir),
      main_js_exists: Boolean(mainJsRel),
      main_css_exists: Boolean(mainCssRel),
    },
    metrics: {},
  };

  if (!mainJsRel || !mainCssRel) {
    report.status = "FAIL";
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    console.error(JSON.stringify(report, null, 2));
    process.exit(1);
  }

  const mainJsPath = path.join(buildDir, mainJsRel.replace(/^\//, ""));
  const mainCssPath = path.join(buildDir, mainCssRel.replace(/^\//, ""));

  report.metrics.main_js = {
    file: mainJsRel,
    ...statWithGzip(mainJsPath),
  };
  report.metrics.main_css = {
    file: mainCssRel,
    ...statWithGzip(mainCssPath),
  };

  const jsGzipKb = report.metrics.main_js.gzip_kb;
  const cssGzipKb = report.metrics.main_css.gzip_kb;
  report.thresholds = thresholdProfiles[thresholdProfile];
  report.threshold_result = {
    main_js_within_limit: jsGzipKb <= report.thresholds.main_js_gzip_kb_max,
    main_css_within_limit: cssGzipKb <= report.thresholds.main_css_gzip_kb_max,
  };

  if (!report.threshold_result.main_js_within_limit || !report.threshold_result.main_css_within_limit) {
    report.status = "WARN";
  }

  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
}

main();

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const { execSync } = require("child_process");

const buildDir = path.join(__dirname, "..", "build");
const reportPath = path.join(buildDir, "perf-smoke-report.json");
const previousReportPath = process.env.PERF_SMOKE_PREV_REPORT || path.join(buildDir, "perf-smoke-report.prev.json");

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

function loadLastFiveBaselineAverages() {
  try {
    const revisionsRaw = execSync("git rev-list --max-count=40 HEAD -- perf-baseline/latest.json", {
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();

    if (!revisionsRaw) {
      return {
        sample_count: 0,
      };
    }

    const revisions = revisionsRaw.split("\n").map((value) => value.trim()).filter(Boolean);
    const samples = [];
    for (const revision of revisions) {
      if (samples.length >= 5) {
        break;
      }
      try {
        const raw = execSync(`git show ${revision}:frontend/perf-baseline/latest.json`, {
          encoding: "utf-8",
          stdio: ["ignore", "pipe", "ignore"],
        });
        const parsed = JSON.parse(raw);
        const js = Number(parsed?.metrics?.main_js?.gzip_kb);
        const css = Number(parsed?.metrics?.main_css?.gzip_kb);
        if (!Number.isFinite(js) || !Number.isFinite(css)) {
          continue;
        }
        samples.push({
          revision,
          main_js_gzip_kb: js,
          main_css_gzip_kb: css,
        });
      } catch {
        // broken commit payload: skip
      }
    }

    if (samples.length === 0) {
      return {
        sample_count: 0,
      };
    }

    const jsAvg = samples.reduce((acc, item) => acc + item.main_js_gzip_kb, 0) / samples.length;
    const cssAvg = samples.reduce((acc, item) => acc + item.main_css_gzip_kb, 0) / samples.length;

    return {
      sample_count: samples.length,
      source: "git-history:frontend/perf-baseline/latest.json",
      main_js_gzip_kb_avg: Number(jsAvg.toFixed(2)),
      main_css_gzip_kb_avg: Number(cssAvg.toFixed(2)),
      revisions: samples.map((item) => item.revision),
    };
  } catch {
    return {
      sample_count: 0,
      error: "git_history_unavailable",
    };
  }
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

  if (fs.existsSync(previousReportPath)) {
    try {
      const previous = JSON.parse(fs.readFileSync(previousReportPath, "utf-8"));
      const prevJs = Number(previous?.metrics?.main_js?.gzip_kb || 0);
      const prevCss = Number(previous?.metrics?.main_css?.gzip_kb || 0);
      report.delta_vs_previous = {
        source: previousReportPath,
        main_js_gzip_kb_delta: Number((report.metrics.main_js.gzip_kb - prevJs).toFixed(2)),
        main_css_gzip_kb_delta: Number((report.metrics.main_css.gzip_kb - prevCss).toFixed(2)),
      };
    } catch {
      report.delta_vs_previous = {
        source: previousReportPath,
        error: "previous_report_parse_failed",
      };
    }
  } else {
    report.delta_vs_previous = {
      source: previousReportPath,
      note: "no_previous_report_found",
    };
  }

  const jsGzipKb = report.metrics.main_js.gzip_kb;
  const cssGzipKb = report.metrics.main_css.gzip_kb;
  report.thresholds = thresholdProfiles[thresholdProfile];
  report.threshold_result = {
    main_js_within_limit: jsGzipKb <= report.thresholds.main_js_gzip_kb_max,
    main_css_within_limit: cssGzipKb <= report.thresholds.main_css_gzip_kb_max,
  };
  report.threshold_utilization = {
    main_js_used_ratio: Number((jsGzipKb / report.thresholds.main_js_gzip_kb_max).toFixed(4)),
    main_css_used_ratio: Number((cssGzipKb / report.thresholds.main_css_gzip_kb_max).toFixed(4)),
  };

  report.last_5_baseline_avg = loadLastFiveBaselineAverages();
  if (Number(report.last_5_baseline_avg?.sample_count || 0) > 0) {
    const avgJs = Number(report.last_5_baseline_avg.main_js_gzip_kb_avg || 0);
    const avgCss = Number(report.last_5_baseline_avg.main_css_gzip_kb_avg || 0);
    const jsDelta = Number((jsGzipKb - avgJs).toFixed(2));
    const cssDelta = Number((cssGzipKb - avgCss).toFixed(2));
    report.delta_vs_last_5_baseline_avg = {
      sample_count: Number(report.last_5_baseline_avg.sample_count || 0),
      main_js_gzip_kb_delta: jsDelta,
      main_css_gzip_kb_delta: cssDelta,
      main_js_deviation_pct: avgJs > 0 ? Number(((jsDelta / avgJs) * 100).toFixed(2)) : null,
      main_css_deviation_pct: avgCss > 0 ? Number(((cssDelta / avgCss) * 100).toFixed(2)) : null,
    };
  } else {
    report.delta_vs_last_5_baseline_avg = {
      sample_count: 0,
      note: "no_last_5_baseline_available",
    };
  }

  if (!report.threshold_result.main_js_within_limit || !report.threshold_result.main_css_within_limit) {
    report.status = "WARN";
  }

  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
}

main();

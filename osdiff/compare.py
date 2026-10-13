from __future__ import annotations

import html
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

from osdiff.fsutil import private_dir, private_file, write_json, write_text


def _load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _normalized_attr(value, cfg):
    value = str(value)
    for pattern in cfg.get("hierarchyIgnoreValuePatterns", []):
        value = re.sub(pattern, "<dynamic>", value)
    return value


def _signature_counts(path, cfg):
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        root = ET.fromstring(raw)
    except Exception as exc:
        return Counter(), f"{type(exc).__name__}: {exc}"

    keys = tuple(
        cfg.get(
            "hierarchyAttributes",
            [
                "type", "class", "name", "label", "resource-id",
                "content-desc", "enabled", "clickable",
            ],
        )
    )
    counts = Counter()

    def walk(element, depth=0, parent_kind="ROOT"):
        attrs = [
            f"{key}={_normalized_attr(element.attrib[key], cfg)}"
            for key in keys
            if element.attrib.get(key) not in (None, "")
        ]
        kind = element.attrib.get("type") or element.attrib.get("class") or element.tag
        if attrs:
            signature = f"depth={depth}|parent={parent_kind}|tag={element.tag}|" + "|".join(attrs)
            counts[signature] += 1
        for child in list(element):
            walk(child, depth + 1, kind)

    walk(root)
    return counts, None


def hierarchy_result(a, b, cfg):
    aa, error_a = _signature_counts(a, cfg)
    bb, error_b = _signature_counts(b, cfg)
    if error_a or error_b:
        return {
            "valid": False,
            "ratio": 0.0,
            "baselineError": error_a,
            "candidateError": error_b,
        }
    if not aa and not bb:
        return {"valid": True, "ratio": 0.0, "baselineError": None, "candidateError": None}
    keys = set(aa) | set(bb)
    intersection = sum(min(aa[key], bb[key]) for key in keys)
    union = sum(max(aa[key], bb[key]) for key in keys)
    return {
        "valid": True,
        "ratio": 1.0 - (intersection / max(1, union)),
        "baselineError": None,
        "candidateError": None,
    }


def hierarchy_ratio(a, b, cfg):
    return hierarchy_result(a, b, cfg)["ratio"]


def _mask_regions(img, regions):
    out = img.copy()
    draw = ImageDraw.Draw(out)
    width, height = out.size
    for region in regions:
        if region.get("normalized"):
            x1 = int(region["x"] * width)
            y1 = int(region["y"] * height)
            x2 = int((region["x"] + region["width"]) * width)
            y2 = int((region["y"] + region["height"]) * height)
        else:
            x1 = int(region["x"])
            y1 = int(region["y"])
            x2 = x1 + int(region["width"])
            y2 = y1 + int(region["height"])
        draw.rectangle((x1, y1, x2, y2), fill=(0, 0, 0))
    return out


def visual(base, cand, diff_out, cfg, platform):
    original_a = Image.open(base).convert("RGB")
    original_b = Image.open(cand).convert("RGB")
    dimension_changed = original_a.size != original_b.size
    resized_b = original_b.resize(original_a.size) if dimension_changed else original_b

    a = _mask_regions(
        original_a, cfg.get("ignoreRegions", {}).get(platform, [])
    )
    b = _mask_regions(
        resized_b, cfg.get("ignoreRegions", {}).get(platform, [])
    )

    # A small configurable blur dampens antialiasing/font rasterization noise between OSes
    # without removing meaningful layout changes.
    blur = float(cfg.get("visualBlurRadius", 0.6))
    if blur > 0:
        a_for_measurement = a.filter(ImageFilter.GaussianBlur(radius=blur))
        b_for_measurement = b.filter(ImageFilter.GaussianBlur(radius=blur))
    else:
        a_for_measurement = a
        b_for_measurement = b

    diff = ImageChops.difference(a_for_measurement, b_for_measurement)
    threshold = int(cfg.get("pixelThreshold", 18))
    total = original_a.size[0] * original_a.size[1]
    r, g, blue = diff.split()
    max_channel = ImageChops.lighter(ImageChops.lighter(r, g), blue)
    histogram = max_channel.histogram()
    changed = sum(histogram[threshold + 1:])
    means = ImageStat.Stat(diff).mean
    delta = sum(means) / (3 * 255)

    # The display overlay uses the unblurred images so reviewers can see real pixels.
    display_diff = ImageChops.difference(a, b)
    mask = display_diff.convert("L").point(lambda value: 255 if value > threshold else 0)
    overlay = Image.new("RGB", original_a.size, (255, 0, 0))
    result = resized_b.copy()
    result.paste(overlay, (0, 0), mask=mask.point(lambda value: int(value * 0.45)))
    result.save(diff_out)

    return {
        "changedPixelRatio": changed / max(1, total),
        "meanDifference": delta,
        "dimensionChanged": dimension_changed,
        "baselineSize": list(original_a.size),
        "candidateSize": list(original_b.size),
    }


def _behavior(baseline_state, candidate_state, cfg):
    out = []
    baseline_assertions = baseline_state.get("assertions", [])
    candidate_assertions = candidate_state.get("assertions", [])
    for index, baseline in enumerate(baseline_assertions):
        candidate = (
            candidate_assertions[index]
            if index < len(candidate_assertions)
            else {"passed": False, "message": "candidate assertion missing"}
        )
        if baseline.get("passed") and not candidate.get("passed"):
            out.append(
                {
                    "type": "assertion_regression",
                    "index": index,
                    "baseline": baseline,
                    "candidate": candidate,
                }
            )

    baseline_actions = baseline_state.get("recentActions", [])
    candidate_actions = candidate_state.get("recentActions", [])
    factor = float(cfg.get("durationRegressionFactor", 1.75))
    extra = float(cfg.get("minimumDurationRegressionSeconds", 1.0))
    for index in range(min(len(baseline_actions), len(candidate_actions))):
        baseline = baseline_actions[index]
        candidate = candidate_actions[index]
        if baseline.get("status") == "passed" and candidate.get("status") == "failed":
            out.append(
                {
                    "type": "action_failure",
                    "index": index,
                    "baseline": baseline,
                    "candidate": candidate,
                }
            )
        else:
            baseline_duration = float(baseline.get("durationSeconds", 0) or 0)
            candidate_duration = float(candidate.get("durationSeconds", 0) or 0)
            if (
                baseline_duration > 0
                and candidate_duration >= baseline_duration * factor
                and candidate_duration - baseline_duration >= extra
            ):
                out.append(
                    {
                        "type": "duration_regression",
                        "index": index,
                        "baselineSeconds": baseline_duration,
                        "candidateSeconds": candidate_duration,
                    }
                )
    return out


def _discover(root):
    root = Path(root)
    out = {}
    if not root.exists():
        return out
    for state in root.glob("*/*/state.json"):
        out[(state.parent.parent.name, state.parent.name)] = state.parent
    return out


def _summary_map(path):
    data = _load(path, []) or []
    return {entry.get("scenario"): entry for entry in data if entry.get("scenario")}


def _execution_results(results_root, platform):
    base_path = Path(results_root) / platform / "baseline" / "run-summary.json"
    cand_path = Path(results_root) / platform / "candidate" / "run-summary.json"
    baseline = _summary_map(base_path)
    candidate = _summary_map(cand_path)
    output = []

    if not base_path.exists():
        output.append(
            {
                "platform": platform,
                "scenario": "__run__",
                "checkpoint": "__execution__",
                "comparisonStatus": "INVALID",
                "riskScore": 100,
                "severity": "Invalid",
                "reasons": ["baseline_run_summary_missing"],
                "behaviorRegressions": [],
                "hierarchyChangeRatio": 0.0,
                "visual": {},
                "missingBaseline": True,
                "missingCandidate": False,
            }
        )
        return output

    if not cand_path.exists():
        output.append(
            {
                "platform": platform,
                "scenario": "__run__",
                "checkpoint": "__execution__",
                "comparisonStatus": "INVALID",
                "riskScore": 100,
                "severity": "Invalid",
                "reasons": ["candidate_run_summary_missing"],
                "behaviorRegressions": [],
                "hierarchyChangeRatio": 0.0,
                "visual": {},
                "missingBaseline": False,
                "missingCandidate": True,
            }
        )
        return output

    for scenario in sorted(set(baseline) | set(candidate)):
        b = baseline.get(scenario)
        c = candidate.get(scenario)
        if b is None:
            output.append(
                {
                    "platform": platform,
                    "scenario": scenario,
                    "checkpoint": "__execution__",
                    "comparisonStatus": "INVALID",
                    "riskScore": 100,
                    "severity": "Invalid",
                    "reasons": ["baseline_scenario_missing"],
                    "behaviorRegressions": [],
                    "hierarchyChangeRatio": 0.0,
                    "visual": {},
                    "missingBaseline": True,
                    "missingCandidate": False,
                }
            )
            continue
        if b.get("status") != "passed":
            output.append(
                {
                    "platform": platform,
                    "scenario": scenario,
                    "checkpoint": "__execution__",
                    "comparisonStatus": "INVALID",
                    "riskScore": 100,
                    "severity": "Invalid",
                    "reasons": ["baseline_execution_failed"],
                    "behaviorRegressions": [
                        {
                            "type": "baseline_execution_failed",
                            "error": b.get("error"),
                        }
                    ],
                    "hierarchyChangeRatio": 0.0,
                    "visual": {},
                    "missingBaseline": False,
                    "missingCandidate": False,
                }
            )
            continue
        if c is None:
            output.append(
                {
                    "platform": platform,
                    "scenario": scenario,
                    "checkpoint": "__execution__",
                    "comparisonStatus": "FAIL",
                    "riskScore": 98,
                    "severity": "Critical",
                    "reasons": ["candidate_scenario_missing"],
                    "behaviorRegressions": [],
                    "hierarchyChangeRatio": 0.0,
                    "visual": {},
                    "missingBaseline": False,
                    "missingCandidate": True,
                }
            )
            continue
        if c.get("status") != "passed":
            output.append(
                {
                    "platform": platform,
                    "scenario": scenario,
                    "checkpoint": "__execution__",
                    "comparisonStatus": "FAIL",
                    "riskScore": 98,
                    "severity": "Critical",
                    "reasons": ["candidate_execution_failed"],
                    "behaviorRegressions": [
                        {
                            "type": "candidate_execution_failed",
                            "error": c.get("error"),
                        }
                    ],
                    "hierarchyChangeRatio": 0.0,
                    "visual": {},
                    "missingBaseline": False,
                    "missingCandidate": False,
                }
            )
    return output


def _score(item, cfg):
    if item["missingCandidate"]:
        return 98, ["checkpoint_missing_on_new_os"]
    if item["missingBaseline"]:
        return 60, ["baseline_coverage_missing"]
    score = 0
    reasons = []
    for behavior in item["behaviorRegressions"]:
        if behavior["type"] in ("assertion_regression", "action_failure"):
            score = max(score, 92)
            reasons.append(behavior["type"])
        elif behavior["type"] == "duration_regression":
            score = max(score, 55)
            reasons.append("performance_regression")

    visual_result = item["visual"]
    if visual_result.get("dimensionChanged"):
        score = max(score, 80)
        reasons.append("screen_dimensions_changed")

    changed_ratio = float(visual_result.get("changedPixelRatio", 0))
    mean_difference = float(visual_result.get("meanDifference", 0))
    if changed_ratio >= float(cfg.get("changedPixelRatioFailure", 0.05)):
        score = max(score, 70)
        reasons.append("large_visual_change")
    elif changed_ratio >= float(cfg.get("changedPixelRatioWarning", 0.01)):
        score = max(score, 45)
        reasons.append("visual_change")

    if mean_difference >= float(cfg.get("meanDifferenceWarning", 0.015)):
        score = max(score, 45)
        reasons.append("mean_visual_difference")

    if item["hierarchyChangeRatio"] >= float(
        cfg.get("hierarchyChangeWarningRatio", 0.15)
    ):
        score = max(score, 50)
        reasons.append("ui_hierarchy_change")
    return score, sorted(set(reasons))


def _severity(score):
    return (
        "Critical"
        if score >= 90
        else "High"
        if score >= 70
        else "Medium"
        if score >= 40
        else "Low"
    )


def compare_platform(results_root, platform, cfg, report_root):
    baseline = _discover(Path(results_root) / platform / "baseline")
    candidate = _discover(Path(results_root) / platform / "candidate")
    assets = private_dir(Path(report_root) / "assets" / platform)
    output = _execution_results(results_root, platform)

    checkpoint_keys = sorted(set(baseline) | set(candidate))
    if not checkpoint_keys:
        # A successful run with zero checkpoints is not a valid compatibility result.
        if not any(item.get("comparisonStatus") == "INVALID" for item in output):
            output.append(
                {
                    "platform": platform,
                    "scenario": "__coverage__",
                    "checkpoint": "__no_checkpoints__",
                    "comparisonStatus": "INVALID",
                    "riskScore": 100,
                    "severity": "Invalid",
                    "reasons": ["no_checkpoints_captured"],
                    "behaviorRegressions": [],
                    "hierarchyChangeRatio": 0.0,
                    "visual": {},
                    "missingBaseline": False,
                    "missingCandidate": False,
                }
            )
        return output

    for scenario, checkpoint in checkpoint_keys:
        baseline_dir = baseline.get((scenario, checkpoint))
        candidate_dir = candidate.get((scenario, checkpoint))
        item = {
            "platform": platform,
            "scenario": scenario,
            "checkpoint": checkpoint,
            "comparisonStatus": "PASS",
            "missingBaseline": baseline_dir is None,
            "missingCandidate": candidate_dir is None,
            "behaviorRegressions": [],
            "hierarchyChangeRatio": 0.0,
            "visual": {},
        }
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{scenario}__{checkpoint}")
        if baseline_dir and candidate_dir:
            baseline_state = _load(baseline_dir / "state.json", {}) or {}
            candidate_state = _load(candidate_dir / "state.json", {}) or {}
            item["behaviorRegressions"] = _behavior(
                baseline_state, candidate_state, cfg
            )
            hierarchy = hierarchy_result(
                baseline_dir / "source.xml", candidate_dir / "source.xml", cfg
            )
            item["hierarchyChangeRatio"] = hierarchy["ratio"]
            item["hierarchyValid"] = hierarchy["valid"]
            if not hierarchy["valid"]:
                item["comparisonStatus"] = "INVALID"
                item["riskScore"] = 100
                item["severity"] = "Invalid"
                item["reasons"] = ["hierarchy_capture_invalid"]
                item["behaviorRegressions"].append({
                    "type": "hierarchy_capture_invalid",
                    "baselineError": hierarchy.get("baselineError"),
                    "candidateError": hierarchy.get("candidateError"),
                })
            baseline_image = assets / f"{safe}__baseline.png"
            candidate_image = assets / f"{safe}__candidate.png"
            diff_image = assets / f"{safe}__diff.png"
            shutil.copyfile(baseline_dir / "screen.png", baseline_image)
            shutil.copyfile(candidate_dir / "screen.png", candidate_image)
            private_file(baseline_image); private_file(candidate_image)
            item["visual"] = visual(
                baseline_image, candidate_image, diff_image, cfg, platform
            )
            item["images"] = {
                "baseline": str(baseline_image.relative_to(report_root)),
                "candidate": str(candidate_image.relative_to(report_root)),
                "diff": str(diff_image.relative_to(report_root)),
            }

        if item.get("comparisonStatus") != "INVALID":
            score, reasons = _score(item, cfg)
            item["riskScore"] = score
            item["severity"] = _severity(score)
            item["reasons"] = reasons
            if score >= 70:
                item["comparisonStatus"] = "FAIL"
            elif score >= 40:
                item["comparisonStatus"] = "REVIEW"
        output.append(item)
    return output


def _e(value):
    return html.escape(str(value), quote=True)


def write_report(report_root, results, project_name="Mobile App", coverage=None, provenance=None):
    report_root = private_dir(report_root)
    results = sorted(
        results,
        key=lambda result: (
            result.get("comparisonStatus") != "INVALID",
            -result["riskScore"],
            result["platform"],
            result["scenario"],
            result["checkpoint"],
        ),
    )
    rows = []
    details = []
    for index, result in enumerate(results):
        reason = ", ".join(result["reasons"]) or "No material regression"
        rows.append(
            f"<tr><td>{_e(result.get('comparisonStatus',''))}</td>"
            f"<td>{result['riskScore']}</td><td>{_e(result['severity'])}</td>"
            f"<td>{_e(result['platform'])}</td><td>{_e(result['scenario'])}</td>"
            f"<td><a href='#d{index}'>{_e(result['checkpoint'])}</a></td>"
            f"<td>{_e(reason)}</td></tr>"
        )
        images = result.get("images", {})
        panels = ""
        if images:
            panels = (
                "<div class='images'>"
                f"<figure><figcaption>Old stable OS</figcaption><img src='{_e(images['baseline'])}'></figure>"
                f"<figure><figcaption>New OS</figcaption><img src='{_e(images['candidate'])}'></figure>"
                f"<figure><figcaption>Highlighted difference</figcaption><img src='{_e(images['diff'])}'></figure>"
                "</div>"
            )
        visual_result = result.get("visual", {})
        behavior_json = _e(json.dumps(result["behaviorRegressions"], indent=2))
        details.append(
            f"<section id='d{index}'><h2>{_e(result['platform'])} · "
            f"{_e(result['scenario'])} · {_e(result['checkpoint'])}</h2>"
            f"<p><b>Status:</b> {_e(result.get('comparisonStatus',''))} &nbsp; "
            f"<b>Risk:</b> {result['riskScore']} ({_e(result['severity'])}) &nbsp; "
            f"<b>Reason:</b> {_e(reason)}</p>"
            f"<p><b>Changed pixels:</b> {visual_result.get('changedPixelRatio',0):.2%} &nbsp; "
            f"<b>Mean difference:</b> {visual_result.get('meanDifference',0):.3%} &nbsp; "
            f"<b>UI hierarchy change:</b> {result.get('hierarchyChangeRatio',0):.2%}</p>"
            f"{panels}<h3>Behavior / execution differences</h3>"
            f"<pre>{behavior_json}</pre></section>"
        )

    css = """body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:28px;line-height:1.45}
.banner-invalid{padding:12px;background:#fff3cd;border:1px solid #e0b800;margin:16px 0}
.coverage-grid{display:flex;gap:16px;flex-wrap:wrap;margin:14px 0 26px}.coverage-card{border:1px solid #ccc;border-radius:8px;padding:12px;min-width:270px;flex:1}.small{font-size:.9em;color:#555}
table{border-collapse:collapse;width:100%;margin-bottom:28px}th,td{border:1px solid #ccc;padding:8px;text-align:left}
th{background:#f3f3f3}.images{display:flex;gap:16px;flex-wrap:wrap}.images figure{width:30%;min-width:250px;margin:0}
.images img{max-width:100%;border:1px solid #aaa}pre{background:#f7f7f7;padding:12px;white-space:pre-wrap}
section{border-top:2px solid #ddd;margin-top:30px;padding-top:16px}"""
    high = sum(
        1
        for result in results
        if result.get("comparisonStatus") != "INVALID" and result["riskScore"] >= 70
    )
    checkpoint_invalid = sum(1 for result in results if result.get("comparisonStatus") == "INVALID")
    review = sum(1 for result in results if result.get("comparisonStatus") == "REVIEW")
    coverage_invalid = bool(coverage) and any(
        item.get("coverageStatus") != "COMPLETE_WITHIN_POLICY"
        for item in coverage.values()
    )
    provenance_invalid = bool(provenance) and not bool((provenance.get("validation") or {}).get("valid"))
    invalid = checkpoint_invalid + int(coverage_invalid) + int(provenance_invalid)
    overall_status = "INVALID" if invalid else ("FAIL" if high else ("REVIEW" if review else "PASS"))
    valid_checkpoints = sum(
        1
        for result in results
        if not result["checkpoint"].startswith("__")
    )
    banner = (
        "<div class='banner-invalid'><b>INVALID comparison:</b> One or more provenance, baseline, execution, hierarchy, "
        "or automatic-coverage prerequisites failed. Do not interpret this run as an OS compatibility PASS.</div>"
        if invalid else ""
    )
    provenance_html = ""
    if provenance:
        cards = []
        for role in ("baseline", "candidate"):
            item = provenance.get(role) or {}
            if not item:
                continue
            market = "VERIFIED" if item.get("marketOriginVerified") else "NOT VERIFIED"
            app_v = item.get("appVersion") or "unknown"
            app_b = item.get("appBuild") or "unknown"
            cards.append(
                "<div class='coverage-card'>"
                f"<h3>{_e(role.upper())}</h3>"
                f"<p><b>Device:</b> {_e(item.get('manufacturer',''))} {_e(item.get('model',''))}<br>"
                f"<b>Device ID:</b> {_e(item.get('deviceIdMasked','<redacted>'))}<br>"
                f"<b>OS:</b> {_e(item.get('osVersion',''))}"
                + (f" / API {_e(item.get('apiLevel'))}" if item.get('apiLevel') else "")
                + f"<br><b>App ID:</b> {_e(item.get('appId',''))}<br>"
                f"<b>Market app:</b> {_e(app_v)} (build {_e(app_b)})<br>"
                f"<b>Market origin:</b> {_e(market)}<br>"
                f"<b>Verification:</b> {_e(item.get('marketOriginMethod',''))}<br>"
                f"<b>Tool installed/replaced app:</b> {_e(item.get('toolInstalledApp', False))}</p>"
                "</div>"
            )
        validation = provenance.get("validation") or {}
        validation_text = "PASS" if validation.get("valid") else "INVALID"
        provenance_html = (
            "<h2>Market-build / real-device provenance</h2>"
            "<p>This mode uses applications already installed on physical devices. "
            "The tool does not sideload or replace the app under test.</p>"
            f"<p><b>Provenance gate:</b> {_e(validation_text)}"
            f" &nbsp; <b>Exact version/build match:</b> {_e(validation.get('sameAppVersionAndBuild', False))}</p>"
            "<div class='coverage-grid'>" + "".join(cards) + "</div>"
        )

    coverage_html = ""
    if coverage:
        cards = []
        for platform_name, item in coverage.items():
            note = item.get("coverageNote") or ""
            cards.append(
                "<div class='coverage-card'>"
                f"<h3>{_e(platform_name.upper())}</h3>"
                f"<p><b>Discovery:</b> {_e(item.get('coverageStatus',''))}</p>"
                f"<p><b>Baseline screens discovered:</b> {int(item.get('discoveredBaselineScreens',0))}<br>"
                f"<b>Candidate screens reproduced:</b> {int(item.get('candidateScreensReproduced',0))}<br>"
                f"<b>Candidate path failures:</b> {int(item.get('candidatePathFailures',0))}<br>"
                f"<b>Blocked unsafe actions:</b> {int(item.get('blockedUnsafeActions',0))}<br>"
                f"<b>Blocked inputs:</b> {int(item.get('blockedInputs',0))}<br>"
                f"<b>Baseline replay failures:</b> {int(item.get('baselineReplayFailures',0))}<br>"
                f"<b>Actions truncated:</b> {int(item.get('actionsTruncated',0))}<br>"
                f"<b>Reset isolation:</b> {_e(item.get('resetIsolationStatus','UNKNOWN'))}</p>"
                f"<p class='small'>{_e(note)}</p>"
                "</div>"
            )
        coverage_html = (
            "<h2>Automatic discovery coverage</h2>"
            "<p>The crawler discovers UI states reachable from the launch state under the configured "
            "credentials, test data, depth/limit settings and safety policy. It must not be interpreted "
            "as proof that every hidden server- or feature-flag-driven state exists in the graph.</p>"
            "<div class='coverage-grid'>" + "".join(cards) + "</div>"
        )
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>OS Differential Regression Report</title>
<style>{css}</style></head><body><h1>{_e(project_name)} — OS Differential Regression Report</h1>
{banner}
{provenance_html}
{coverage_html}
<p>Compared the same app journeys on the old stable OS and the new OS. Functional differences are weighted more heavily than visual changes.</p>
<p><b>Overall status:</b> {_e(overall_status)} &nbsp; <b>Valid checkpoints:</b> {valid_checkpoints} &nbsp; <b>High/Critical:</b> {high} &nbsp; <b>Review:</b> {review} &nbsp; <b>Invalid:</b> {invalid}</p>
<table><thead><tr><th>Status</th><th>Risk</th><th>Severity</th><th>Platform</th><th>Scenario</th><th>Checkpoint</th><th>Reason</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>{''.join(details)}</body></html>"""
    write_text(report_root / "index.html", body)
    write_json(report_root / "comparison.json", results)
    summary = {
        "overallStatus": overall_status,
        "checkpoints": valid_checkpoints,
        "highRisk": high,
        "review": review,
        "invalid": invalid,
        "checkpointInvalid": checkpoint_invalid,
        "coverageInvalid": coverage_invalid,
        "provenanceInvalid": provenance_invalid,
        "report": str(report_root / "index.html"),
    }
    write_json(report_root / "summary.json", summary)
    return summary

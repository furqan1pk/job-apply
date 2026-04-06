"""PDF report generator — visual proof of each application."""

import csv
import json
from datetime import datetime
from pathlib import Path


def generate_html_report(results_dir: str = "results", screenshots_dir: str = "screenshots") -> str:
    """Generate an HTML report with screenshots from today's batch run.

    Returns the path to the generated HTML file.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    results_path = Path(results_dir)
    screenshots_path = Path(screenshots_dir)

    # Load today's results
    jsonl_file = results_path / f"applications_{date_str}.jsonl"
    if not jsonl_file.exists():
        print(f"No results found for {date_str}")
        return ""

    results = []
    with open(jsonl_file, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))

    # Build HTML
    html_parts = [
        "<!DOCTYPE html>",
        "<html><head>",
        "<meta charset='utf-8'>",
        f"<title>Job Applications Report - {date_str}</title>",
        "<style>",
        "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #0d1117; color: #c9d1d9; }",
        "h1 { color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }",
        "h2 { color: #c9d1d9; margin-top: 40px; }",
        ".job-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin: 20px 0; }",
        ".status-applied { color: #3fb950; font-weight: bold; }",
        ".status-failed { color: #f85149; font-weight: bold; }",
        ".status-captcha { color: #d29922; font-weight: bold; }",
        ".status-dry_run { color: #58a6ff; font-weight: bold; }",
        ".status-skipped { color: #8b949e; font-weight: bold; }",
        ".meta { color: #8b949e; font-size: 0.9em; margin: 5px 0; }",
        ".screenshots { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px; }",
        ".screenshots img { max-width: 380px; border: 1px solid #30363d; border-radius: 4px; cursor: pointer; }",
        ".screenshots img:hover { border-color: #58a6ff; }",
        "table { width: 100%; border-collapse: collapse; margin: 20px 0; }",
        "th, td { padding: 8px 12px; border: 1px solid #30363d; text-align: left; }",
        "th { background: #161b22; color: #58a6ff; }",
        "a { color: #58a6ff; text-decoration: none; }",
        "a:hover { text-decoration: underline; }",
        ".summary { display: flex; gap: 30px; margin: 20px 0; }",
        ".summary-stat { background: #161b22; padding: 15px 25px; border-radius: 8px; border: 1px solid #30363d; }",
        ".summary-stat .num { font-size: 2em; font-weight: bold; }",
        ".summary-stat .label { color: #8b949e; }",
        "</style>",
        "</head><body>",
        f"<h1>Job Applications Report</h1>",
        f"<p class='meta'>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Total: {len(results)} applications</p>",
    ]

    # Summary stats
    applied = sum(1 for r in results if r["status"] == "applied")
    failed = sum(1 for r in results if r["status"] == "failed")
    captcha = sum(1 for r in results if r["status"] == "captcha")
    dry_run = sum(1 for r in results if r["status"] == "dry_run")

    html_parts.append("<div class='summary'>")
    html_parts.append(f"<div class='summary-stat'><div class='num' style='color:#3fb950'>{applied}</div><div class='label'>Applied</div></div>")
    html_parts.append(f"<div class='summary-stat'><div class='num' style='color:#f85149'>{failed}</div><div class='label'>Failed</div></div>")
    html_parts.append(f"<div class='summary-stat'><div class='num' style='color:#d29922'>{captcha}</div><div class='label'>CAPTCHA</div></div>")
    html_parts.append(f"<div class='summary-stat'><div class='num' style='color:#58a6ff'>{dry_run}</div><div class='label'>Dry Run</div></div>")
    html_parts.append("</div>")

    # Summary table
    html_parts.append("<table>")
    html_parts.append("<tr><th>#</th><th>Company</th><th>Title</th><th>Status</th><th>Time</th><th>Link</th></tr>")
    for i, r in enumerate(results, 1):
        status_class = f"status-{r['status']}"
        html_parts.append(
            f"<tr><td>{i}</td><td>{r.get('company','')}</td><td>{r.get('job_title','')}</td>"
            f"<td class='{status_class}'>{r['status'].upper()}</td>"
            f"<td>{r.get('duration_sec', 0):.0f}s</td>"
            f"<td><a href='{r['url']}' target='_blank'>View</a></td></tr>"
        )
    html_parts.append("</table>")

    # Per-job screenshots
    html_parts.append("<h2>Application Screenshots</h2>")

    for i, r in enumerate(results, 1):
        title = r.get("job_title", "Unknown")
        company = r.get("company", "")
        status = r["status"]
        status_class = f"status-{status}"

        html_parts.append(f"<div class='job-card'>")
        html_parts.append(f"<h3>{i}. {title} @ {company}</h3>")
        html_parts.append(f"<p class='meta'>Status: <span class='{status_class}'>{status.upper()}</span> | Duration: {r.get('duration_sec',0):.0f}s</p>")
        if r.get("error"):
            html_parts.append(f"<p class='meta' style='color:#f85149'>Error: {r['error'][:200]}</p>")
        html_parts.append(f"<p class='meta'><a href='{r['url']}' target='_blank'>{r['url']}</a></p>")

        # Find screenshots for this job
        safe_company = "".join(c if c.isalnum() or c in "._-" else "_" for c in company[:20])
        safe_title = "".join(c if c.isalnum() or c in "._-" else "_" for c in title[:20])
        matching = sorted(screenshots_path.glob(f"*{safe_company}*")) + sorted(screenshots_path.glob(f"*{safe_title}*"))

        # Deduplicate
        seen = set()
        unique_shots = []
        for s in matching:
            if s.name not in seen:
                seen.add(s.name)
                unique_shots.append(s)

        if unique_shots:
            html_parts.append("<div class='screenshots'>")
            for shot in unique_shots:
                html_parts.append(f"<a href='{shot}' target='_blank'><img src='{shot}' alt='{shot.stem}'></a>")
            html_parts.append("</div>")
        else:
            html_parts.append("<p class='meta'>No screenshots captured</p>")

        html_parts.append("</div>")

    html_parts.append("</body></html>")

    # Write HTML
    report_path = results_path / f"report_{date_str}.html"
    report_path.write_text("\n".join(html_parts), encoding="utf-8")
    print(f"\nReport saved: {report_path}")
    return str(report_path)


if __name__ == "__main__":
    path = generate_html_report()
    if path:
        import os
        os.startfile(path)  # Open in browser on Windows

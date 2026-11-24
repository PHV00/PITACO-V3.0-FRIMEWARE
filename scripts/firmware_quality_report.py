#!/usr/bin/env python3
"""Render a human-readable Actions report and enforce a first-party quality gate."""
import argparse
from collections import Counter
import html
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

DIAG = re.compile(r"^(.*?):(\d+):(\d+):\s+(warning|error):\s+(.*?)(?:\s+\[([^\]]+)\])?$", re.I)


def source_location(raw, root):
    value = (raw or "").replace("\\", "/")
    if "/.arduino15/" in value or value.startswith("/usr/") or value.startswith("/opt/"):
        return "dependency", value, False
    if "/.pitaco-static-" in value or value.endswith(".ino.cpp"):
        return "generated", value, False
    workspace = Path(root).resolve()
    path = Path(value)
    if not path.is_absolute():
        path = workspace / path
    try:
        relative = path.resolve().relative_to(workspace).as_posix()
    except ValueError:
        return "dependency", value, False
    if relative.startswith("frimeware2.4/src/vendor_"):
        return "vendor", relative, False
    owned = relative.startswith("frimeware2.4/") or relative.startswith("test/")
    return ("first-party" if owned else "other"), relative, owned and path.is_file()


def parse(reports, workspace):
    findings, failures = [], []
    try:
        root = ET.parse(reports / "cppcheck.xml").getroot()
        if root.tag != "results":
            raise ValueError("unexpected root element")
        for element in root.findall(".//error"):
            location = element.find("location")
            path = location.get("file", "") if location is not None else element.get("file0", "")
            category, source, linkable = source_location(path, workspace)
            findings.append({
                "tool": "Cppcheck", "category": category,
                "severity": element.get("severity", "unknown"),
                "rule": element.get("id", "unknown"),
                "message": element.get("msg", ""),
                "path": source,
                "line": int(location.get("line", "0")) if location is not None else 0,
                "linkable": linkable
            })
    except (OSError, ET.ParseError, ValueError) as exc:
        failures.append("Cppcheck XML missing or invalid: " + str(exc))

    def read_exit(name):
        try:
            return int((reports / (name + "-exit-code.txt")).read_text().strip())
        except (ValueError, OSError):
            failures.append("Missing or invalid exit status for " + name)
            return None

    cpp_code = read_exit("cppcheck")
    if cpp_code not in (0, 2):
        failures.append("Cppcheck did not finish successfully (exit %s)" % cpp_code)
    if cpp_code == 2 and not any(f["tool"] == "Cppcheck" for f in findings):
        failures.append("Cppcheck exited with findings, but the XML has none")
    clang_code = read_exit("clang-tidy")
    if clang_code != 0:
        failures.append("Clang-Tidy host G1 analysis failed (exit %s)" % clang_code)
    try:
        for line in (reports / "clang-tidy.txt").read_text(errors="replace").splitlines():
            match = DIAG.match(line.strip())
            if not match:
                continue
            source, number, _, severity, message, rule = match.groups()
            category, filename, linkable = source_location(source, workspace)
            findings.append({
                "tool": "Clang-Tidy", "category": category,
                "severity": severity.lower(), "rule": rule or "clang-diagnostic",
                "message": message, "path": filename,
                "line": int(number), "linkable": linkable
            })
    except OSError as exc:
        failures.append("Clang-Tidy text missing: " + str(exc))
    blocking = [f for f in findings if f["category"] == "first-party"
                and f["severity"] == "error"]
    if blocking:
        failures.append("%d first-party analyzer error(s)" % len(blocking))
    return findings, failures, {"cppcheck": cpp_code, "clang-tidy": clang_code}


def generate(reports, workspace):
    reports.mkdir(parents=True, exist_ok=True)
    findings, failures, exits = parse(reports, workspace)
    owned = [x for x in findings if x["category"] == "first-party"]
    state = "FAIL" if failures else "PASS"
    counts = Counter((x["tool"], x["category"]) for x in findings)
    summary = ["## PITACO — firmware quality report", "",
               "**Quality gate: %s**" % state, "",
               "| Analyzer | First-party findings | External/generated findings | Exit code |",
               "|---|---:|---:|---:|"]
    for tool, key, label in [
        ("Cppcheck", "cppcheck", "Cppcheck: compiled ESP32-C3 sketch"),
        ("Clang-Tidy", "clang-tidy", "Clang-Tidy: production G1 via host C++ test")
    ]:
        own = counts[(tool, "first-party")]
        ext = sum(count for (name, category), count in counts.items()
                  if name == tool and category != "first-party")
        summary.append("| %s | %d | %d | %s |" % (label, own, ext, exits[key]))
    summary += ["",
                "**Enforced:** all analyzers run successfully, XML is valid, and no "
                "first-party severity=error finding. Other findings are visible for triage.",
                "",
                "**Scope:** Cppcheck analyses the generated Arduino sketch and dependency "
                "headers; Clang-Tidy analyses the same SQI Gate 01 code through its "
                "native C++ test, not the whole ESP32 sketch. Hardware tests are separate.",
                ""]
    if failures:
        summary += ["### Blocking reasons", ""]
        summary.extend("- " + reason for reason in failures)
        summary.append("")
    summary += ["### First-party findings (%d)" % len(owned), "",
                "| Tool | Severity | Check | File : line | Finding |",
                "|---|---|---|---|---|"]
    for x in owned[:35]:
        escape_md = lambda item: str(item).replace("|", "\\|").replace("\n", " ")
        summary.append("| %s | %s | %s | %s:%d | %s |" % (
            escape_md(x["tool"]), escape_md(x["severity"]),
            escape_md(x["rule"]), escape_md(x["path"]),
            x["line"], escape_md(x["message"])))
    if not owned:
        summary.append("| — | — | — | — | No first-party diagnostics |")
    summary += ["", "Complete table: download artifact and open report.html. "
                "Raw logs, issues.json and the original Cppcheck XML are included.", ""]
    markdown = "\n".join(summary)
    (reports / "SUMMARY.md").write_text(markdown, encoding="utf-8")
    (reports / "issues.json").write_text(json.dumps(
        {"gate": state, "exit_codes": exits, "failures": failures, "findings": findings},
        ensure_ascii=False, indent=2), encoding="utf-8")
    with (reports / "report.html").open("w", encoding="utf-8") as handle:
        handle.write('<!DOCTYPE html><html><meta charset="utf-8">'
                     '<title>PITACO firmware quality report</title>'
                     '<style>body{font:14px system-ui;max-width:1250px;margin:2em auto}'
                     'table{border-collapse:collapse;width:100%}th,td{border:1px solid #999;'
                     'padding:7px;text-align:left;vertical-align:top}th{background:#eee}'
                     'tr:nth-child(even){background:#f7f7f7}.fail{color:#b00}</style>')
        handle.write('<h1>Firmware quality gate: %s</h1>' % state)
        handle.write('<p>First-party issues are separated from dependencies and '
                     'generated Arduino build files. Non-error warnings remain visible.</p>')
        if failures:
            handle.write("<h2>Blocking reasons</h2><ul>")
            for reason in failures:
                handle.write("<li>%s</li>" % html.escape(reason))
            handle.write("</ul>")
        handle.write("<h2>All %d findings</h2><table><tr>" % len(findings))
        handle.write("".join("<th>%s</th>" % h for h in
                    ("Tool", "Category", "Severity", "Rule", "Source", "Line", "Message")))
        handle.write("</tr>")
        for x in findings:
            handle.write("<tr>" + "".join("<td>%s</td>" % html.escape(str(x[field]))
                for field in ("tool", "category", "severity", "rule", "path", "line", "message"))
                + "</tr>")
        handle.write("</table></html>")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(markdown)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for x in owned[:30]:
            if not x["linkable"] or not x["line"]:
                continue
            category = "error" if x["severity"] == "error" else "warning"
            msg = ("%s [%s] %s" % (x["tool"], x["rule"], x["message"]))
            msg = msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print("::%s file=%s,line=%d::%s" % (category, x["path"], x["line"], msg))
        for reason in failures:
            print("::error::" + reason.replace("%", "%25"))
    print("Firmware quality: %s | first-party=%d external=%d" % (
        state, len(owned), len(findings) - len(owned)))
    return 1 if failures else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--reports", default="reports")
    p.add_argument("--workspace", default=os.getcwd())
    args = p.parse_args()
    sys.exit(generate(Path(args.reports), Path(args.workspace)))

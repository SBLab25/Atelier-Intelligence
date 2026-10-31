"""Final Spec 02 numbers from gate3 junit and the final smoke logs -> final-numbers.txt"""
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ev, repo = Path(sys.argv[1]), Path(sys.argv[2])
out = []


def read(p):
    if not p.exists():
        return ""
    raw = p.read_bytes()
    return raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")


root = ET.parse(ev / "gate3-pytest-junit.xml").getroot()
by_module = Counter()
failed_by_module = Counter()
for c in root.iter("testcase"):
    mod = c.get("classname", "").split(".")[1] if "." in c.get("classname", "") else c.get("classname")
    by_module[mod] += 1
    if c.find("failure") is not None or c.find("error") is not None:
        failed_by_module[mod] += 1
out.append("tests per module (passed/total):")
for m in sorted(by_module):
    out.append(f"   {m}: {by_module[m] - failed_by_module[m]}/{by_module[m]}")
out.append(f"   TOTAL: {sum(by_module.values()) - sum(failed_by_module.values())}/{sum(by_module.values())}")

demo = read(ev / "final-demo-pipeline.log")
out.append("demo pipeline:")
for pat in (r"\[OK\] data_worker[^\n]*", r"\[OK\] friction_worker[^\n]*", r"\[OK\] insight_worker[^\n]*",
            r"\[OK\] report_worker[^\n]*", r"\[DONE\][^\n]*", r"Max iterations[^\n]*"):
    m = re.search(pat, demo)
    out.append("   " + (m.group(0)[:160] if m else f"(no match: {pat})"))

ing = read(ev / "final-ingest-probe.log")
out.append("ingest probe:")
out.append("   routes->ingestion_worker=%d  404s=%d  8005 posts=%d  8004/tools=%d  max-iteration hits=%d" % (
    len(re.findall(r"Route .*ingestion_worker", ing)), len(re.findall(r"\b404\b", ing)),
    len(re.findall(r"8005/messages", ing)), len(re.findall(r"8004/tools", ing)), len(re.findall(r"Max iterations", ing))))
for pat in (r"\[OK\] ingestion_worker[^\n]*", r"Low confidence[^\n]*", r"ingestion_worker error[^\n]*",
            r"\[OK\] data_worker[^\n]*", r"\[DONE\][^\n]*"):
    m = re.search(pat, ing)
    out.append("   " + (m.group(0)[:160] if m else f"(no match: {pat})"))

for p in (repo / "System.Xml.XmlElement", repo / "cji_agent" / "System.Xml.XmlElement"):
    if p.exists():
        out.append(f"stray file {p.relative_to(repo)}: {p.stat().st_size} bytes, first line: {read(p).splitlines()[:1]}")

(ev / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")

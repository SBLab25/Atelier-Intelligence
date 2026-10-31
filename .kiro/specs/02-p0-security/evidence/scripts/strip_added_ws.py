"""Strip trailing spaces/tabs only on lines added in the working-tree diff (keeps CRLF)."""
import re
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1])
diff = subprocess.run(["git", "-C", str(repo), "diff", "-U0", "--no-color"],
                      capture_output=True, text=True, encoding="utf-8").stdout
targets, current = {}, None
for line in diff.splitlines():
    if line.startswith("+++ b/"):
        current = repo / line[6:]
    elif line.startswith("@@") and current is not None:
        m = re.search(r"\+(\d+)(?:,(\d+))?", line)
        start, count = int(m.group(1)), int(m.group(2) or 1)
        targets.setdefault(current, set()).update(range(start, start + count))
for path, nums in targets.items():
    raw = path.read_bytes().decode("utf-8")
    lines = raw.split("\r\n")
    fixed = 0
    for n in nums:
        if 0 < n <= len(lines) and lines[n - 1] != lines[n - 1].rstrip(" \t"):
            lines[n - 1] = lines[n - 1].rstrip(" \t")
            fixed += 1
    if fixed:
        path.write_bytes("\r\n".join(lines).encode("utf-8"))
        print(f"{path.relative_to(repo)}: stripped {fixed} line(s)")

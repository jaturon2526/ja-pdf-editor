"""สรุปผล load test (run.sh เรียก) → ตาราง markdown: ต่อขั้นจำนวนผู้ใช้ — req/s, เวลาตอบ, ล้มเหลว, CPU/RAM สูงสุดของ container"""
import csv
import re
import sys
from pathlib import Path

out = Path(sys.argv[1])
stages = []  # (users, start_time)
if (out / "stages.csv").exists():
    for row in csv.reader(open(out / "stages.csv")):
        stages.append((int(row[1]), row[2]))


def mem_mib(text):
    m = re.match(r"([\d.]+)\s*([KMG]i?B)", text.strip())
    if not m:
        return 0.0
    v, u = float(m.group(1)), m.group(2)
    return v * {"KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024}.get(u, 1)


stats = []
if (out / "server-stats.csv").exists():
    for row in csv.DictReader(open(out / "server-stats.csv")):
        try:
            stats.append((row["time"], row["container"], row["cpu"], row["mem"]))
        except KeyError:
            pass


def peaks(start, end):
    res = {}
    for t, name, cpu, mem in stats:
        if t < start or (end and t >= end):
            continue
        used = mem.split("/")[0]
        c = float(cpu.rstrip("%")) if cpu not in ("-", "") else 0.0
        p = res.setdefault(name, [0.0, 0.0])
        p[0] = max(p[0], c)
        p[1] = max(p[1], mem_mib(used))
    return res


workers = (out / "backend-workers.txt").read_text().strip() if (out / "backend-workers.txt").exists() else ""
print(f"# ผล load test — {out.name}" + (f" (backend {workers} worker)" if workers else "") + "\n")
print("| ผู้ใช้ | คำขอ/วินาที | render หน้า p50 / p95 (ms) | แก้ไข p95 (ms) | บันทึก p95 (ms) | บีบอัด p95 (ms) | ล้มเหลว | CPU backend สูงสุด | RAM backend สูงสุด | RAM เครื่อง สูงสุด |")
print("|---|---|---|---|---|---|---|---|---|---|")
for i, (users, start) in enumerate(stages):
    f = out / f"stage-{users}_stats.csv"
    if not f.exists():
        continue
    rows = {r["Name"]: r for r in csv.DictReader(open(f))}
    agg = rows.get("Aggregated", {})
    g = lambda name, col: rows.get(name, {}).get(col, "-")  # noqa: E731
    reqs = int(agg.get("Request Count", 0) or 0)
    fails = int(agg.get("Failure Count", 0) or 0)
    end = stages[i + 1][1] if i + 1 < len(stages) else None
    pk = peaks(start, end)
    be = pk.get("pdf_backend_prod", [0, 0])
    host = pk.get("HOST", [0, 0])
    rps = float(agg.get("Requests/s", 0) or 0)
    print(f"| {users} | {rps:.1f} | {g('render page', '50%')} / {g('render page', '95%')} | {g('add annotation', '95%')} | "
          f"{g('save', '95%')} | {g('compress (heavy)', '95%')} | {100 * fails / reqs if reqs else 0:.1f}% | "
          f"{be[0]:.0f}% | {be[1]:.0f} MiB | {host[1]:.0f} MiB |")
print("\nCPU 100% = 1 core (เครื่องมี 4 core = สูงสุด 400%) · รายละเอียดแต่ละขั้นดูไฟล์ stage-*.html")
err = out / "backend-errors.log"
if err.exists() and err.stat().st_size:
    print(f"\nมี error ใน log ของ backend ช่วงทดสอบ — ดู {err.name}")

import hashlib, json, os, platform, shutil, subprocess, sys, time, zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
TIMEOUT = 60
RETRIES = 4
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"


def log(lines, msg):
    print(msg, flush=True)
    lines.append(msg)


def downloader():
    # GitHub-hosted Ubuntu/Windows runners both have curl available.
    for name in ("curl.exe", "curl"):
        p = shutil.which(name)
        if p:
            return p
    raise RuntimeError("curl was not found on the runner")


def curl_download(url, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass

    curl = downloader()
    cmd = [curl, "-L", "--fail", "--silent", "--show-error",
           "--retry", str(RETRIES), "--retry-all-errors",
           "--connect-timeout", str(TIMEOUT), "--max-time", str(TIMEOUT * 2),
           "-A", UA, "-H", "Accept: */*", "-o", str(tmp)]
    if platform.system().lower().startswith("win"):
        cmd.insert(1, "--ssl-no-revoke")
    # The exchange archives respond more reliably with the correct referer.
    referer = "https://www.nseindia.com/" if "nseindia.com" in url else "https://www.bseindia.com/"
    cmd += ["-H", f"Referer: {referer}", url]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        try: tmp.unlink()
        except FileNotFoundError: pass
        raise RuntimeError(p.stderr.strip() or f"curl exit {p.returncode}")
    if not tmp.exists() or tmp.stat().st_size < 50:
        try: tmp.unlink()
        except FileNotFoundError: pass
        raise RuntimeError("empty or tiny response")
    tmp.replace(out)


def valid(path):
    if not path.exists() or path.stat().st_size < 50:
        return False
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                return bool(z.namelist())
        except Exception:
            return False
    # Reject obvious HTML error pages saved with a CSV/DAT/GZ extension.
    try:
        with path.open("rb") as f:
            head = f.read(200).lstrip().lower()
        if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            return False
    except Exception:
        return False
    return True


def nse_urls(d):
    dd = d.strftime("%d%m%Y")
    ymd = d.strftime("%Y%m%d")
    yy = d.strftime("%y%m%d")
    return {
        "udiff": f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip",
        "full": f"https://nsearchives.nseindia.com/content/cm/sec_bhavdata_full_{dd}.csv",
        "52w": f"https://nsearchives.nseindia.com/content/CM_52_wk_High_low_{dd}.csv",
        "delivery": f"https://nsearchives.nseindia.com/content/nsccl/MTO_{dd}.DAT",
        "market_activity": f"https://nsearchives.nseindia.com/content/cm/MA{yy}.csv",
        "volatility": f"https://nsearchives.nseindia.com/content/CMVOLT_{yy}.CSV",
        "security": f"https://nsearchives.nseindia.com/content/cm/NSE_CM_security_{ymd}.csv.gz",
    }


def bse_urls(d):
    ymd = d.strftime("%Y%m%d")
    ddmmyy = d.strftime("%d%m%y")
    return [
        # Current BSE CM-UDiFF-style daily CSV used by maintained BSE clients.
        f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV",
        # Legacy daily equity ZIP retained as a second official BSE source.
        f"https://www.bseindia.com/download/BhavCopy/Equity/EQ{ddmmyy}_CSV.ZIP",
    ]


def core_available(d):
    # A usable date requires one current NSE CM-UDiFF bhavcopy and one
    # official BSE equity bhavcopy. We deliberately avoid third-party mirrors.
    probe_dir = OUT / ".probe"
    probe_dir.mkdir(parents=True, exist_ok=True)

    nse_path = probe_dir / "nse_udiff.zip"
    try:
        if not valid(nse_path):
            curl_download(nse_urls(d)["udiff"], nse_path)
        nse_ok = valid(nse_path)
    except Exception:
        nse_ok = False

    bse_ok = False
    for i, url in enumerate(bse_urls(d), 1):
        ext = ".zip" if url.lower().endswith(".zip") else ".csv"
        path = probe_dir / f"bse_{i}{ext}"
        try:
            if not valid(path):
                curl_download(url, path)
            if valid(path):
                bse_ok = True
                break
        except Exception:
            pass
    return [("NSE", "udiff", nse_urls(d)["udiff"], nse_path if nse_ok else None, nse_ok),
            ("BSE", "equity_bhavcopy", bse_urls(d)[0], None if not bse_ok else path, bse_ok)]


def collect_for_date(d, lines):
    day = OUT / f"{d:%Y-%m-%d}"
    day.mkdir(parents=True, exist_ok=True)
    specs = [
        ("NSE", "udiff", ".zip", nse_urls(d)["udiff"]),
        ("NSE", "full", ".csv", nse_urls(d)["full"]),
        ("NSE", "52w", ".csv", nse_urls(d)["52w"]),
        ("NSE", "delivery", ".DAT", nse_urls(d)["delivery"]),
        ("NSE", "market_activity", ".csv", nse_urls(d)["market_activity"]),
        ("NSE", "volatility", ".CSV", nse_urls(d)["volatility"]),
        ("NSE", "security", ".gz", nse_urls(d)["security"]),
    ]
    records = []
    for exch, kind, ext, url in specs:
        out = day / f"{exch.lower()}_{kind}{ext}"
        rec = {"exchange": exch, "kind": kind, "url": url, "file": str(out.relative_to(ROOT))}
        try:
            if not valid(out):
                curl_download(url, out)
            if not valid(out):
                raise RuntimeError("validation failed")
            rec.update(status="ok", bytes=out.stat().st_size,
                       sha256=hashlib.sha256(out.read_bytes()).hexdigest())
            log(lines, f"OK   {exch:3} {kind:20} {rec['bytes']:>10} bytes")
        except Exception as e:
            rec.update(status="failed", error=str(e))
            log(lines, f"WARN {exch:3} {kind:20} {e}")
        records.append(rec)

    # BSE official daily CM-UDiFF-style CSV first, then official legacy ZIP.
    bse_rec = None
    for i, url in enumerate(bse_urls(d), 1):
        suffix = ".ZIP" if url.lower().endswith(".zip") else ".CSV"
        out = day / f"bse_equity_bhavcopy_{i}{suffix}"
        try:
            if not valid(out):
                curl_download(url, out)
            if valid(out):
                bse_rec = {"exchange":"BSE", "kind":"equity_bhavcopy",
                           "source":"official_bse", "url":url,
                           "file":str(out.relative_to(ROOT)), "status":"ok",
                           "bytes":out.stat().st_size,
                           "sha256":hashlib.sha256(out.read_bytes()).hexdigest()}
                log(lines, f"OK   BSE equity_bhavcopy source-{i} {bse_rec['bytes']:>10} bytes")
                break
        except Exception as e:
            log(lines, f"WARN BSE source-{i} {e}")
    if bse_rec is None:
        bse_rec = {"exchange":"BSE", "kind":"equity_bhavcopy",
                   "source":"official_bse", "url":bse_urls(d)[0], "file":"",
                   "status":"failed", "error":"Official BSE sources unavailable"}
    records.append(bse_rec)
    (day / "manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    return records


def make_bundle(day):
    bundle = OUT / f"bundle_{day:%Y-%m-%d}.zip"
    folder = OUT / day.strftime("%Y-%m-%d")
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(OUT))
    return bundle


def main():
    OUT.mkdir(exist_ok=True)
    lines = [f"NSE+BSE EOD collector started {datetime.now():%Y-%m-%d %H:%M:%S} UTC"]
    chosen = None

    for d in (date.today() - timedelta(days=i) for i in range(7)):
        log(lines, f"Checking trading date {d:%Y-%m-%d} ...")
        probes = core_available(d)
        if all(x[4] for x in probes):
            chosen = d
            log(lines, f"Core NSE+BSE files found for {d:%Y-%m-%d}.")
            break
        log(lines, f"Core files not both available for {d:%Y-%m-%d}; trying previous day.")

    if chosen is None:
        (OUT / "RUN_REPORT.txt").write_text("\n".join(lines + ["STATUS: FAILED — no usable NSE+BSE trading date found in last 7 days."]), encoding="utf-8")
        raise SystemExit(2)

    records = collect_for_date(chosen, lines)
    bundle = make_bundle(chosen)
    ok = sum(r["status"] == "ok" for r in records)
    fail = len(records) - ok
    status = "SUCCESS" if fail == 0 else "PARTIAL — core NSE+BSE data available; auxiliary files may be unavailable."
    lines += [f"SELECTED TRADING DATE: {chosen:%Y-%m-%d}", f"FILES OK: {ok}", f"FILES FAILED: {fail}", f"BUNDLE: {bundle}", f"STATUS: {status}"]
    (OUT / "RUN_REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

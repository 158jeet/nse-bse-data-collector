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


def bse_url(d):
    return f"https://www.bseindia.com/download/BhavCopy/Equity/EQ{d.strftime('%d%m%y')}_CSV.ZIP"


def bse_fallback_url(d):
    # Free BSE-derived UDiFF-compatible fallback.  The direct BSE archive
    # is retained as the preferred source; this is used when BSE blocks
    # GitHub-hosted runners or the legacy archive is unavailable.
    return (f"https://mtf.trading/api/v1/bhavcopy?date={d:%Y-%m-%d}"
            f"&exchange=bse&series=EQ&format=csv&limit=100000")


def core_available(d):
    # Download the two files that determine whether this is a usable trading date.
    probe_dir = OUT / ".probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    results = []
    specs = [
        ("NSE", "full", ".csv", nse_urls(d)["full"]),
    ]
    for exch, kind, ext, url in specs:
        path = probe_dir / f"{exch.lower()}_{kind}{ext}"
        try:
            if not valid(path):
                curl_download(url, path)
            ok = valid(path)
            results.append((exch, kind, url, path if ok else None, ok))
        except Exception:
            results.append((exch, kind, url, None, False))

    # BSE direct archive first. If the exchange blocks the GitHub runner,
    # use the free UDiFF-compatible BSE EOD mirror as a network fallback.
    bse_direct = probe_dir / "bse_equity_bhavcopy.ZIP"
    bse_ok = False
    try:
        if not valid(bse_direct):
            curl_download(bse_url(d), bse_direct)
        bse_ok = valid(bse_direct)
    except Exception:
        bse_ok = False
    if bse_ok:
        results.append(("BSE", "equity_bhavcopy", bse_url(d), bse_direct, True))
    else:
        bse_fallback = probe_dir / "bse_equity_bhavcopy_fallback.csv"
        try:
            if not valid(bse_fallback):
                curl_download(bse_fallback_url(d), bse_fallback)
            ok = valid(bse_fallback)
            results.append(("BSE", "equity_bhavcopy", bse_fallback_url(d), bse_fallback if ok else None, ok))
        except Exception:
            results.append(("BSE", "equity_bhavcopy", bse_fallback_url(d), None, False))
    return results


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

    # BSE direct archive, then free UDiFF-compatible fallback if direct access
    # is blocked from the GitHub runner.
    bse_targets = [
        ("bse_equity_bhavcopy.ZIP", bse_url(d), "bse_direct"),
        ("bse_equity_bhavcopy_fallback.csv", bse_fallback_url(d), "bse_udiff_fallback"),
    ]
    bse_rec = None
    for filename, url, source in bse_targets:
        out = day / filename
        try:
            if not valid(out):
                curl_download(url, out)
            if valid(out):
                bse_rec = {"exchange":"BSE", "kind":"equity_bhavcopy", "source":source,
                           "url":url, "file":str(out.relative_to(ROOT)),
                           "status":"ok", "bytes":out.stat().st_size,
                           "sha256":hashlib.sha256(out.read_bytes()).hexdigest()}
                log(lines, f"OK   BSE equity_bhavcopy ({source}) {bse_rec['bytes']:>10} bytes")
                break
        except Exception as e:
            log(lines, f"WARN BSE {source:20} {e}")
    if bse_rec is None:
        bse_rec = {"exchange":"BSE", "kind":"equity_bhavcopy", "source":"direct+fallback",
                   "url":bse_url(d), "file":"", "status":"failed",
                   "error":"BSE direct archive and fallback unavailable"}
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

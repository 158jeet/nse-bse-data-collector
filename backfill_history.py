import csv, io, os, shutil, subprocess, tempfile, zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "history"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
TIMEOUT = 45
RETRIES = 3
CHUNK = 500
OUT_COLS = ["exchange","symbol","isin","series","open","high","low","close","prev_close","volume","value","trades"]


def curl(url, out):
    curl_bin = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_bin:
        raise RuntimeError("curl not found")
    cmd = [curl_bin, "-L", "--fail", "--silent", "--show-error", "--retry", str(RETRIES),
           "--retry-all-errors", "--connect-timeout", str(TIMEOUT), "--max-time", str(TIMEOUT*2),
           "-A", UA, "-H", "Accept: */*", "-o", str(out), "-H", "Referer: " +
           ("https://nsearchives.nseindia.com/" if "nseindia.com" in url else "https://www.bseindia.com/"), url]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode or not Path(out).exists() or Path(out).stat().st_size < 100:
        raise RuntimeError(p.stderr.strip() or f"curl exit {p.returncode}")


def clean(v):
    return "" if v is None else str(v).strip()


def num(v):
    try: return float(clean(v).replace(",", ""))
    except: return None


def urls(d):
    ymd = d.strftime("%Y%m%d")
    ddmmyy = d.strftime("%d%m%y")
    return (
        f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip",
        f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV",
        f"https://www.bseindia.com/download/BhavCopy/Equity/EQ{ddmmyy}_CSV.ZIP",
    )


def read_csv(path_or_bytes, zipped=False):
    if zipped:
        with zipfile.ZipFile(path_or_bytes) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            if not names: raise RuntimeError("zip contains no CSV")
            data = z.read(names[0]).decode("utf-8-sig", errors="replace")
        return csv.DictReader(io.StringIO(data))
    return csv.DictReader(open(path_or_bytes, "r", encoding="utf-8-sig", errors="replace", newline=""))


def extract(src, exchange, zipped=False):
    r = read_csv(src, zipped)
    rows = []
    for row in r:
        if clean(row.get("FinInstrmTp")) != "STK": continue
        isin, symbol, series, close = clean(row.get("ISIN")), clean(row.get("TckrSymb")), clean(row.get("SctySrs")), num(row.get("ClsPric"))
        if not isin.startswith("INE") or not symbol or close is None: continue
        if exchange == "NSE" and series not in {"EQ", "BE"}: continue
        if exchange == "BSE" and series in {"F","G","GB","GS","MF","ETF"}: continue
        rows.append({"exchange":exchange,"symbol":symbol,"isin":isin,"series":series,
                     "open":clean(row.get("OpnPric")),"high":clean(row.get("HghPric")),"low":clean(row.get("LwPric")),
                     "close":clean(row.get("ClsPric")),"prev_close":clean(row.get("PrvsClsgPric")),
                     "volume":clean(row.get("TtlTradgVol")),"value":clean(row.get("TtlTrfVal")),"trades":clean(row.get("TtlNbOfTxsExctd"))})
    return rows


def write(rows, out):
    rows.sort(key=lambda x: x["symbol"])
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS); w.writeheader(); w.writerows(rows)


def existing_dates():
    if not HISTORY.exists(): return set()
    return {p.name for p in HISTORY.iterdir() if p.is_dir() and len(p.name)==10 and p.name[4]=='-' and (p/'nse_equity.csv').exists() and (p/'bse_equity.csv').exists()}


def main():
    HISTORY.mkdir(exist_ok=True)
    # Build approximately 60 trading sessions of history from the last 90 calendar days.
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=90)
    done = existing_dates()
    candidates = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d.isoformat() not in done: candidates.append(d)
        d += timedelta(days=1)

    print(f"History already has {len(done)} complete dates; attempting {len(candidates)} missing weekdays.", flush=True)
    added = 0
    for d in candidates:
        nse_url, bse_url, bse_legacy = urls(d)
        with tempfile.TemporaryDirectory() as td:
            nse = Path(td)/"nse.zip"; bse = Path(td)/"bse.csv"
            try:
                curl(nse_url, nse)
                curl(bse_url, bse)
            except Exception:
                try:
                    if not nse.exists(): curl(nse_url, nse)
                    curl(bse_legacy, bse)
                except Exception:
                    print(f"SKIP {d}: official NSE/BSE daily files unavailable", flush=True)
                    continue
            try:
                nr = extract(nse, "NSE", True)
                br = extract(bse, "BSE", False)
                if not nr or not br: raise RuntimeError("empty classified equity set")
                dest = HISTORY/d.isoformat(); dest.mkdir(parents=True, exist_ok=True)
                write(nr, dest/"nse_equity.csv"); write(br, dest/"bse_equity.csv")
                (dest/"README.txt").write_text(f"Trading date: {d}\nNSE equity rows: {len(nr)}\nBSE equity rows: {len(br)}\nData-only historical EOD handoff; no ranking or trading decisions.\n", encoding="utf-8")
                added += 1
                print(f"OK   {d}  NSE={len(nr)} BSE={len(br)}", flush=True)
            except Exception as e:
                print(f"SKIP {d}: {e}", flush=True)
    print(f"History backfill complete. Added {added} dates; total complete dates now {len(existing_dates())}.", flush=True)

if __name__ == "__main__": main()

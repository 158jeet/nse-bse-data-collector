import csv, math
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "history"
LATEST = ROOT / "latest"
CHUNK = 300

OUT_COLS = [
    "exchange","symbol","isin","series","date","close","prev_close","volume","value","trades",
    "sma20","sma50","sma200","avg_vol20","volume_ratio20","high20","high50","high60",
    "low20","low50","low60","high252","low252","dist_52w_high_pct","dist_52w_low_pct",
    "roc20_pct","roc50_pct","rsi14","atr14_pct","range_pct","close_vs_sma20_pct","close_vs_sma50_pct",
    "close_vs_sma200_pct","sma20_slope20_pct","sma50_slope20_pct"
]

def f(x):
    try:
        v = float(str(x).replace(",", "").strip())
        return v if math.isfinite(v) else None
    except Exception:
        return None

def pct(a, b):
    return None if a is None or b in (None, 0) else (a / b - 1.0) * 100.0

def sma(vals, n):
    vals = list(vals)[-n:]
    return sum(vals) / n if len(vals) == n else None

def rsi(closes, n=14):
    if len(closes) < n + 1: return None
    gains, losses = [], []
    for a, b in zip(closes[-n-1:-1], closes[-n:]):
        d = b - a
        gains.append(max(d, 0.0)); losses.append(max(-d, 0.0))
    ag, al = sum(gains)/n, sum(losses)/n
    if al == 0: return 100.0 if ag > 0 else 50.0
    return 100.0 - (100.0 / (1.0 + ag/al))

def atr_pct(rows, n=14):
    if len(rows) < n + 1: return None
    trs = []
    for i in range(len(rows)-n, len(rows)):
        hi, lo = rows[i]["high"], rows[i]["low"]
        prev = rows[i-1]["close"]
        if None in (hi, lo, prev): return None
        trs.append(max(hi-lo, abs(hi-prev), abs(lo-prev)))
    c = rows[-1]["close"]
    return None if not c else sum(trs)/n/c*100.0

def read_history():
    data = defaultdict(list)
    for d in sorted(p for p in HISTORY.iterdir() if p.is_dir()):
        for ex in ("nse", "bse"):
            path = d / f"{ex}_equity.csv"
            if not path.exists(): continue
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
                for r in csv.DictReader(fh):
                    isin, sym, series = r.get("isin", "").strip(), r.get("symbol", "").strip(), r.get("series", "").strip()
                    c = f(r.get("close")); o, h, l = f(r.get("open")), f(r.get("high")), f(r.get("low"))
                    if not isin or not sym or c is None: continue
                    data[(ex.upper(), isin)].append({
                        "date": d.name, "symbol": sym, "isin": isin, "series": series,
                        "open": o, "high": h, "low": l, "close": c,
                        "prev_close": f(r.get("prev_close")), "volume": f(r.get("volume")),
                        "value": f(r.get("value")), "trades": f(r.get("trades"))
                    })
    return data

def make_row(rows):
    r = rows[-1]; closes = [x["close"] for x in rows]
    vols = [x["volume"] for x in rows if x["volume"] is not None]
    c = r["close"]
    s20, s50, s200 = sma(closes,20), sma(closes,50), sma(closes,200)
    av20 = sma(vols,20)
    high20 = max(x["high"] for x in rows[-20:] if x["high"] is not None) if len(rows)>=20 else None
    high50 = max(x["high"] for x in rows[-50:] if x["high"] is not None) if len(rows)>=50 else None
    high60 = max(x["high"] for x in rows[-60:] if x["high"] is not None) if len(rows)>=60 else None
    low20 = min(x["low"] for x in rows[-20:] if x["low"] is not None) if len(rows)>=20 else None
    low50 = min(x["low"] for x in rows[-50:] if x["low"] is not None) if len(rows)>=50 else None
    low60 = min(x["low"] for x in rows[-60:] if x["low"] is not None) if len(rows)>=60 else None
    h252 = max(x["high"] for x in rows if x["high"] is not None)
    l252 = min(x["low"] for x in rows if x["low"] is not None)
    # Slopes compare today's MA with the MA computed 20 observations ago.
    s20_old = sma(closes[:-20],20) if len(closes)>=40 else None
    s50_old = sma(closes[:-20],50) if len(closes)>=70 else None
    return {
        "exchange": r["exchange"] if "exchange" in r else "", "symbol": r["symbol"], "isin": r["isin"], "series": r["series"],
        "date": r["date"], "close": r["close"], "prev_close": r["prev_close"], "volume": r["volume"], "value": r["value"], "trades": r["trades"],
        "sma20": s20, "sma50": s50, "sma200": s200, "avg_vol20": av20,
        "volume_ratio20": (r["volume"]/av20 if r["volume"] is not None and av20 else None),
        "high20": high20, "high50": high50, "high60": high60, "low20": low20, "low50": low50, "low60": low60,
        "high252": h252, "low252": l252, "dist_52w_high_pct": pct(c,h252), "dist_52w_low_pct": pct(c,l252),
        "roc20_pct": pct(c, closes[-21]) if len(closes)>=21 else None,
        "roc50_pct": pct(c, closes[-51]) if len(closes)>=51 else None,
        "rsi14": rsi(closes), "atr14_pct": atr_pct(rows),
        "range_pct": pct(r["high"], r["low"]) if r["high"] is not None and r["low"] else None,
        "close_vs_sma20_pct": pct(c,s20), "close_vs_sma50_pct": pct(c,s50), "close_vs_sma200_pct": pct(c,s200),
        "sma20_slope20_pct": pct(s20,s20_old), "sma50_slope20_pct": pct(s50,s50_old)
    }

def fmt(v):
    if v is None: return ""
    if isinstance(v, float): return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)

def main():
    data = read_history()
    rows_out = []
    for (ex, isin), rows in data.items():
        rows.sort(key=lambda x: x["date"])
        # Require at least 20 observations; longer history improves 50/200-day fields when available.
        if len(rows) < 20: continue
        for x in rows: x["exchange"] = ex
        rows_out.append(make_row(rows))
    rows_out.sort(key=lambda x: (x["symbol"], x["exchange"], x["isin"]))
    LATEST.mkdir(exist_ok=True)
    for p in LATEST.glob("technical_snapshot_*.csv"): p.unlink()
    for n, start in enumerate(range(0, len(rows_out), CHUNK), 1):
        path = LATEST / f"technical_snapshot_{n:03d}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=OUT_COLS); w.writeheader()
            for row in rows_out[start:start+CHUNK]: w.writerow({k:fmt(row.get(k)) for k in OUT_COLS})
    (LATEST / "TECHNICAL_SNAPSHOT_README.txt").write_text(
        "Pure data transformation only; no ranking, scoring, stock selection or trading decision is generated here.\n"
        f"Symbols with >=20 observations: {len(rows_out)}\n"
        "Indicators use only the available historical EOD archive. 52-week fields are the maximum/minimum in the archived history, not a claim of a complete calendar-year history unless 252 sessions are present.\n"
        "SMA200 and related fields remain blank until sufficient observations exist.\n",
        encoding="utf-8")
    print(f"Technical snapshot complete: {len(rows_out)} exchange-symbol histories.")

if __name__ == "__main__": main()

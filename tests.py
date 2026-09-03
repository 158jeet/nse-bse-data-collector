import ast, json, tempfile, zipfile
from pathlib import Path
from datetime import date
import collector

ast.parse(Path("collector.py").read_text(encoding="utf-8"))
assert collector.bse_urls(date(2026,9,3))[0].endswith("BhavCopy_BSE_CM_0_0_0_20260903_F_0000.CSV")
assert collector.bse_urls(date(2026,9,3))[1].endswith("EQ030926_CSV.ZIP")
u=collector.nse_urls(date(2026,9,3))
assert u["udiff"].endswith("_20260903_F_0000.csv.zip")
assert u["full"].endswith("sec_bhavdata_full_03092026.csv")
assert u["52w"].endswith("CM_52_wk_High_low_03092026.csv")
assert u["delivery"].endswith("MTO_03092026.DAT")
assert u["market_activity"].endswith("MA260903.csv")
assert u["volatility"].endswith("CMVOLT_260903.CSV")
assert u["security"].endswith("NSE_CM_security_20260903.csv.gz")
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"x.zip"
    with zipfile.ZipFile(p,"w") as z: z.writestr("x.csv","a,b\n1,2\n")
    assert collector.valid(p)
print("ALL LOCAL TESTS PASSED")

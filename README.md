# NSE + BSE EOD Data Collector (tested package)

This is a small **data-only** collector. It does not rank stocks, calculate buy/sell signals, place orders, or connect to a broker.

It downloads official/public exchange EOD files and produces a dated folder plus a single ZIP bundle.

## One-click use on Windows 11

1. Keep this folder on your PC.
2. Double-click `RUN_DAILY.bat`.
3. The collector automatically searches today and recent prior business days for the latest available files.
4. When complete, it creates:
   `output\bundle_YYYY-MM-DD.zip`
5. Upload that ZIP to ChatGPT when you want me to analyze the data.

No command-line debugging should be necessary. If a source is unavailable, the run creates a clear `RUN_REPORT.txt` and exits with a useful message.

## Data sources
NSE:
- UDiFF common bhavcopy
- Full bhavcopy + security deliverable data
- 52-week high/low
- security-wise delivery positions
- market activity
- daily volatility
- security master

BSE:
- Equity daily bhavcopy

NSE's current reports page confirms the above EOD report families and notes that the old bhavcopy/common-bhavcopy formats were discontinued in July 2024 in favor of UDiFF. BSE's legacy public equity bhavcopy endpoint is used for the BSE EOD file.

## Important limitation
The generated files are local. ChatGPT cannot automatically read an arbitrary folder on your PC. For the PC phase, upload the generated bundle here. Once this data pipeline is proven, we can move only the collector to cloud storage/API for automatic daily consumption.

## Safety
No Upstox token, API key, secret, order permission, or trading endpoint is used.

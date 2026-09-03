# GitHub Actions setup

This repository is a data-only NSE/BSE EOD collector. It does not rank stocks or place trades.

The workflow runs Monday-Friday at about 7:00 PM IST and can also be started manually from GitHub Actions.

Each successful run creates an artifact containing the latest available NSE+BSE trading-day bundle. Artifacts are retained for 14 days.

The collector automatically handles weekends/holidays by checking back up to seven calendar days and requires both core NSE and BSE equity bhavcopy files before selecting a date.

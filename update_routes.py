name: Update routes

on:
  workflow_dispatch:
    inputs:
      force_update:
        description: GTFSを強制的に再取得する
        type: boolean
        default: false
      force_stats_update:
        description: e-Statの家賃データを強制的に再取得する
        type: boolean
        default: false
  schedule:
    - cron: "0 18 * * 0"

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install packages
        run: pip install requests pandas

      - name: Update data
        run: python update_routes.py
        env:
          ESTAT_APP_ID: ${{ secrets.ESTAT_APP_ID }}
          FORCE_UPDATE: ${{ inputs.force_update || false }}
          FORCE_STATS_UPDATE: ${{ inputs.force_stats_update || false }}

      - name: Commit updated files
        run: |
          git config user.name github-actions
          git config user.email actions@github.com
          git add direct_timetable.json station_locations.json unresolved_stations.json municipality_stats.json data
          git diff --cached --quiet || (git commit -m "Update timetable and municipality data" && git push)

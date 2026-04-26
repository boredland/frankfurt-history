# POIs with bad coordinates (upstream API data)

These entries have coordinates that are clearly wrong (UTM values, truncated, or otherwise outside Frankfurt).
They are filtered out by `geojson.py` and won't appear on the map until fixed.

## To fix

Create an override in `overrides/de/<theme>/<slug>.md` with corrected coordinates.

## Entries

| POI | Raw coordinates | Issue |
|-----|----------------|-------|
| `frankfurt-und-der-ns/2264-zweitwohnung-von-g-wild` | `[5010414, 866404]` | UTM values, not WGS84 |
| `frankfurt-und-der-ns/2265-zuhause-von-erna-fleischhauer` | `[50.1233304, 866923]` | Longitude is UTM easting |

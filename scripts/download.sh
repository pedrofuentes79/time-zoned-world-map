#!/usr/bin/env bash
# Descarga los datos de origen a data/raw/ (~170 MB).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw && cd data/raw

TZB=2026c
echo ">> timezone-boundary-builder $TZB"
for f in timezones-now timezones-with-oceans-now; do
  curl -sL -o tmp.zip \
    "https://github.com/evansiroky/timezone-boundary-builder/releases/download/$TZB/$f.geojson.zip"
  unzip -o -q tmp.zip && rm tmp.zip
done

echo ">> Natural Earth 10m"
for f in ne_10m_land ne_10m_minor_islands ne_10m_geography_marine_polys \
         ne_10m_geography_regions_polys; do
  curl -sL -o "$f.zip" "https://naciscdn.org/naturalearth/10m/physical/$f.zip"
done
curl -sL -o ne_10m_admin_0_countries.zip \
  "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"

echo "listo"

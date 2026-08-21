#!/usr/bin/env python3
"""Erzeugt static/world.svg aus Natural Earth 1:110m.

Wird nicht ins Image kopiert und läuft nicht zur Laufzeit — die fertige Datei
liegt im Repository. Neu erzeugen nur, wenn die Umrisse veraltet sind:

    python tools/make_world_svg.py

Quelle: https://github.com/nvkelso/natural-earth-vector (Public Domain).
Projektion: Plate carrée, also x = Längengrad, y = Breitengrad — damit lassen
sich Koordinaten aus CrowdSec ohne Bibliothek in Bildpunkte umrechnen.
"""

import json
import pathlib
import urllib.request

SOURCE = ('https://raw.githubusercontent.com/nvkelso/natural-earth-vector/'
          'master/geojson/ne_110m_admin_0_countries.geojson')
OUT = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'world.svg'

# Ausschnitt wie bei üblichen Webkarten: oben 84° Nord, unten 60° Süd. Die
# Antarktis fällt damit raus — sie ist in dieser Projektion riesig und hat für
# eine Angriffskarte keinen Aussagewert.
LAT_TOP = 84.0
LAT_BOTTOM = -60.0
DECIMALS = 1


def project(lon: float, lat: float) -> tuple:
    return round(lon + 180.0, DECIMALS), round(90.0 - lat, DECIMALS)


def ring_to_path(ring: list) -> str:
    """Ein Polygonring als SVG-Pfadsegment, ohne doppelte Punkte."""
    out, last = [], None
    for point in ring:
        try:
            x, y = project(float(point[0]), float(point[1]))
        except (TypeError, ValueError, IndexError):
            continue
        if (x, y) == last:
            continue
        out.append(f'{x:g},{y:g}')
        last = (x, y)
    if len(out) < 3:
        return ''
    return 'M' + 'L'.join(out) + 'Z'


def polygons(geometry: dict):
    kind = geometry.get('type')
    coords = geometry.get('coordinates') or []
    if kind == 'Polygon':
        yield coords
    elif kind == 'MultiPolygon':
        yield from coords


def country_code(props: dict) -> str:
    """Natural Earth trägt für umstrittene Gebiete "-99" ein; dann lieber
    ohne Code zeichnen, als einen falschen zu erfinden."""
    for key in ('ISO_A2_EH', 'ISO_A2'):
        code = str(props.get(key) or '').strip().upper()
        if len(code) == 2 and code.isalpha():
            return code
    return ''


def main() -> None:
    print('lade', SOURCE)
    with urllib.request.urlopen(SOURCE, timeout=60) as resp:
        data = json.loads(resp.read().decode('utf-8'))

    parts = []
    for feature in data.get('features') or []:
        props = feature.get('properties') or {}
        code = country_code(props)
        if code == 'AQ':
            continue
        segments = []
        for polygon in polygons(feature.get('geometry') or {}):
            for ring in polygon:
                seg = ring_to_path(ring)
                if seg:
                    segments.append(seg)
        if not segments:
            continue
        attr = f' data-cc="{code}"' if code else ''
        name = str(props.get('NAME') or '').replace('"', '')
        parts.append(f'<path class="cc"{attr} data-name="{name}" '
                     f'd="{"".join(segments)}"/>')

    top, bottom = 90.0 - LAT_TOP, 90.0 - LAT_BOTTOM
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="0 {top:g} 360 {bottom - top:g}" '
           f'preserveAspectRatio="xMidYMid meet">'
           + ''.join(parts) + '</svg>')

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding='utf-8')
    print(f'{OUT} — {len(parts)} Länder, {len(svg) / 1024:.0f} KB')


if __name__ == '__main__':
    main()

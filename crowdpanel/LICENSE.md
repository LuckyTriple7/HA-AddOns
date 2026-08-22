# Lizenzen — CrowdPanel

Der Programmcode dieses Add-ons steht unter der MIT-Lizenz des Repositorys
(siehe [../LICENSE](../LICENSE)). Diese Datei nennt die Bestandteile, die von
woanders stammen.

## Weltkarte — `static/world.svg`

Erzeugt aus **Natural Earth**, Datensatz `ne_110m_admin_0_countries`, bezogen
über [natural-earth-vector](https://github.com/nvkelso/natural-earth-vector).

> All versions of Natural Earth raster and vector map data found on this website
> are in the public domain. You may use the maps in any manner, including
> modifying the content and design, electronic dissemination, and offset
> printing. The primary authors, Tom Patterson and Nathaniel Vaughn Kelso, and
> all other contributors renounce all financial claim to the maps and invite you
> to use them for personal, educational, and commercial purposes.

— <https://www.naturalearthdata.com/about/terms-of-use/>

Public Domain, also keine Auflagen. Die Nennung hier steht aus Höflichkeit und
damit nachvollziehbar bleibt, woher die Umrisse kommen.

Erzeugt wird die Datei mit `tools/make_world_svg.py`; das Skript wandert nicht
ins Image und läuft nicht zur Laufzeit.

## Python-Abhängigkeiten

Siehe `requirements.txt`. Alle unter eigenen, permissiven Lizenzen:

| Paket | Lizenz |
|---|---|
| Flask | BSD-3-Clause |
| requests | Apache-2.0 |
| qrcode | BSD-3-Clause |

## CrowdSec

CrowdPanel enthält keinen CrowdSec-Code und kein CrowdSec-Image. Es spricht
ausschließlich über HTTP mit einer bereits vorhandenen Installation. CrowdSec
selbst steht unter der MIT-Lizenz.

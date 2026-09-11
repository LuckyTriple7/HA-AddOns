#!/usr/bin/env python3
"""Lokaler Start ohne Container.

    python3 dev_run.py

Setzt die Pfade auf den Quellordner und legt Daten in dev_data/ ab (in
.gitignore). Wird nicht ins Image kopiert.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

os.environ.setdefault('REACTORSIM_BASE', _HERE)
os.environ.setdefault('REACTORSIM_DATA', os.path.join(_HERE, 'dev_data'))
os.environ.setdefault('REACTORSIM_PORT', '17779')

sys.path.insert(0, _HERE)

import app  # noqa: E402

if __name__ == '__main__':
    os.makedirs(os.environ['REACTORSIM_DATA'], exist_ok=True)
    print(f"ReactorSim {app.APP_VERSION} — http://127.0.0.1:{app.PORT}")
    app._serve()

"""TripPilot-Fragebogen aus /config/trippilot/questions.json: Validierung,
Fallback auf die mitgelieferte Datei und die daraus abgeleiteten Prompt-Felder.
"""
import importlib
import json

import pytest

import trippilot_questions as TQ


BUNDLED = json.load(open(TQ.BUNDLED_PATH, encoding='utf-8'))


@pytest.fixture
def tq(tmp_path, monkeypatch):
    """Loader mit eigenem Fragen-Ordner im tmp_path (Cache je Test leer)."""
    d = tmp_path / 'trippilot'
    d.mkdir()
    monkeypatch.setattr(TQ, 'QUESTIONS_DIR', str(d))
    monkeypatch.setattr(TQ, 'QUESTIONS_PATH', str(d / 'questions.json'))
    monkeypatch.setattr(TQ, 'DEFAULT_COPY_PATH', str(d / 'questions.default.json'))
    monkeypatch.setattr(TQ, 'README_PATH', str(d / 'README.md'))
    TQ._cache.update({'mtime': None, 'path': None, 'data': None})
    yield TQ
    TQ._cache.update({'mtime': None, 'path': None, 'data': None})


def write(tq, data):
    with open(tq.QUESTIONS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


# ── Mitgelieferte Datei ────────────────────────────────────────────────────────

def test_bundled_file_is_valid():
    assert TQ.validate(BUNDLED) == []


def test_bundled_daytrip_value_is_a_region_option():
    region = next(s for s in BUNDLED['steps'] if s['key'] == 'region')
    assert BUNDLED['daytrip_value'] in region['options']


def test_bundled_has_no_duplicate_keys():
    keys = [s['key'] for s in BUNDLED['steps']]
    assert len(keys) == len(set(keys))


# ── Validierung ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('data', [
    'kein Objekt',
    {},
    {'steps': []},
    {'steps': [{'key': 'a', 'title': 'T', 'label': 'L'}]},                    # type fehlt
    {'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'bogus'}]},   # type unbekannt
    {'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'multi'}]},   # options fehlen
    {'steps': [{'title': 'T', 'label': 'L', 'type': 'text'}]},                # key fehlt
    {'steps': [{'key': 'a', 'label': 'L', 'type': 'text'}]},                  # title fehlt
    {'steps': [{'key': 'a', 'title': 'T', 'type': 'text'}]},                  # label fehlt
    {'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'text', 'options': ['x']}]},
    {'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'multi', 'options': ['x', 'x']}]},
    {'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'multi', 'options': ['x'],
                'exclusive': ['nicht in options']}]},
])
def test_validate_rejects(data):
    assert TQ.validate(data)


def test_validate_rejects_duplicate_keys():
    step = {'key': 'a', 'title': 'T', 'label': 'L', 'type': 'text'}
    errors = TQ.validate({'steps': [step, dict(step)]})
    assert any('doppelter Key' in e for e in errors)


@pytest.mark.parametrize('cond', [
    {'key': 'unbekannt', 'contains': 'x'},        # Key existiert nicht
    {'key': 'a'},                                 # kein Operator
    {'key': 'a', 'contains': 'x', 'equals': 'y'},  # zwei Operatoren
    {'key': 'a', 'contains_any': 'kein Array'},
    {'key': 'a', 'answered': 'ja'},               # kein Bool
    {'all': []},                                  # leere Verknuepfung
    {'all': [{'key': 'unbekannt', 'contains': 'x'}]},
    {'not': {'key': 'unbekannt', 'contains': 'x'}},
    'kein Objekt',
])
def test_validate_rejects_bad_conditions(cond):
    data = {'steps': [
        {'key': 'a', 'title': 'T', 'label': 'L', 'type': 'multi', 'options': ['x']},
        {'key': 'b', 'title': 'T', 'label': 'L', 'type': 'text', 'show_if': cond},
    ]}
    assert TQ.validate(data)


def test_validate_accepts_forward_reference():
    """Eine Bedingung darf sich auf eine spaeter definierte Frage beziehen."""
    data = {'steps': [
        {'key': 'a', 'title': 'T', 'label': 'L', 'type': 'text',
         'show_if': {'key': 'b', 'answered': True}},
        {'key': 'b', 'title': 'T', 'label': 'L', 'type': 'multi', 'options': ['x']},
    ]}
    assert TQ.validate(data) == []


# ── Laden / Fallback ───────────────────────────────────────────────────────────

def test_load_without_user_file_uses_bundled(tq):
    q = tq.load(force=True)
    assert q['source'] == 'bundled'
    assert q['errors'] == []
    assert [s['key'] for s in q['steps']] == [s['key'] for s in BUNDLED['steps']]


def test_load_prefers_valid_user_file(tq):
    write(tq, {'daytrip_value': 'Ausflug',
               'steps': [{'key': 'nur_eine', 'title': 'Frage?', 'label': 'Feld',
                          'type': 'single', 'options': ['ja', 'nein']}]})
    q = tq.load(force=True)
    assert q['source'] == 'user'
    assert [s['key'] for s in q['steps']] == ['nur_eine']
    assert q['daytrip_value'] == 'Ausflug'


def test_broken_json_falls_back_and_reports(tq):
    with open(tq.QUESTIONS_PATH, 'w', encoding='utf-8') as f:
        f.write('{ das ist kein JSON')
    q = tq.load(force=True)
    assert q['source'] == 'bundled'
    assert q['errors']
    assert len(q['steps']) == len(BUNDLED['steps'])


def test_invalid_schema_falls_back_and_reports(tq):
    write(tq, {'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'bogus'}]})
    q = tq.load(force=True)
    assert q['source'] == 'bundled'
    assert any('type' in e for e in q['errors'])


def test_cache_refreshes_after_file_change(tq):
    write(tq, {'steps': [{'key': 'erste', 'title': 'T', 'label': 'L', 'type': 'text'}]})
    assert [s['key'] for s in tq.load()['steps']] == ['erste']
    import os
    import time
    write(tq, {'steps': [{'key': 'zweite', 'title': 'T', 'label': 'L', 'type': 'text'}]})
    os.utime(tq.QUESTIONS_PATH, (time.time() + 5, time.time() + 5))
    assert [s['key'] for s in tq.load()['steps']] == ['zweite']


# ── Anlegen / Update-Verhalten ─────────────────────────────────────────────────

def test_ensure_user_copy_creates_files(tq):
    import os
    assert tq.ensure_user_copy() is True
    assert os.path.exists(tq.QUESTIONS_PATH)
    assert os.path.exists(tq.DEFAULT_COPY_PATH)
    assert os.path.exists(tq.README_PATH)


def test_ensure_user_copy_never_overwrites_user_file(tq):
    """Kernpunkt fuers Add-on-Update: eigene Fragen bleiben erhalten, die
    Referenzdatei wird auf den neuen Auslieferungsstand gehoben."""
    own = {'steps': [{'key': 'meine_frage', 'title': 'T', 'label': 'L', 'type': 'text'}]}
    write(tq, own)
    tq.ensure_user_copy()
    with open(tq.QUESTIONS_PATH, encoding='utf-8') as f:
        assert json.load(f) == own
    with open(tq.DEFAULT_COPY_PATH, encoding='utf-8') as f:
        assert json.load(f) == BUNDLED


# ── Ableitungen fuer den Prompt ────────────────────────────────────────────────

def test_derived_fields_match_step_types(tq):
    write(tq, {'steps': [
        {'key': 'm', 'title': 'T', 'label': 'Mehrfach', 'type': 'multi', 'options': ['x']},
        {'key': 's', 'title': 'T', 'label': 'Einzeln', 'type': 'single', 'options': ['x']},
        {'key': 't', 'title': 'T', 'label': 'Text', 'type': 'text'},
    ]})
    tq.load(force=True)
    assert tq.fields() == ('m', 's', 't')          # Reihenfolge = Prompt-Reihenfolge
    assert tq.list_fields() == {'m'}
    assert tq.text_fields() == {'t'}
    assert tq.labels() == {'m': 'Mehrfach', 's': 'Einzeln', 't': 'Text'}


def test_bundled_derivation_matches_previous_hardcoded_sets():
    """Regression: die bis 0.89.x fest im Code stehenden Feldlisten muessen sich
    unveraendert aus der ausgelieferten JSON ergeben."""
    steps = BUNDLED['steps']
    assert tuple(s['key'] for s in steps) == (
        'region', 'excluded_countries', 'excluded_countries_other', 'interests',
        'beach_detail', 'berge_detail', 'travel_type', 'companions', 'budget',
        'duration', 'duration_daytrip', 'month', 'temp', 'water_type', 'sea', 'rain',
        'activities', 'accommodation', 'accommodation_size', 'hotel_wishes',
        'arrival_mode', 'home_location', 'max_distance', 'flight_time', 'airports',
        'dislikes', 'perfect_holiday', 'past_trips', 'perfect_daytrip')
    assert {s['key'] for s in steps if s['type'] == 'multi'} == {
        'interests', 'beach_detail', 'berge_detail', 'travel_type', 'activities',
        'hotel_wishes', 'airports', 'dislikes', 'excluded_countries', 'water_type', 'region'}
    assert {s['key'] for s in steps if s['type'] == 'text'} == {
        'perfect_holiday', 'past_trips', 'excluded_countries_other',
        'home_location', 'perfect_daytrip'}
    assert {s['key']: s['label'] for s in steps}['region'] == 'Ziel-Region'


def test_module_imports_without_config_dir():
    """Der Loader darf beim Import nichts anlegen oder lesen (kein /config im Test)."""
    importlib.reload(TQ)


# ── API-Endpunkt ───────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch, tq):
    """Flask-Testclient mit dem tmp_path-Fragenordner aus der `tq`-Fixture."""
    pytest.importorskip("flask")
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        m = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(m)
    m.DB_PATH = str(tmp_path / "tuiwatch.db")
    m.init_db()
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    m.app.config["TESTING"] = True
    return m.app.test_client()


def test_questions_endpoint_serves_bundled_by_default(client, tq):
    d = client.get("/api/trippilot/questions").get_json()
    assert d["source"] == "bundled" and d["errors"] == []
    assert [s["key"] for s in d["steps"]] == [s["key"] for s in BUNDLED["steps"]]
    assert d["daytrip_value"] == BUNDLED["daytrip_value"]


def test_questions_endpoint_serves_user_file(client, tq):
    write(tq, {"daytrip_value": "Ausflug",
               "steps": [{"key": "eigene", "title": "Frage?", "label": "Feld",
                          "type": "single", "options": ["ja"]}]})
    tq.load(force=True)
    d = client.get("/api/trippilot/questions").get_json()
    assert d["source"] == "user"
    assert [s["key"] for s in d["steps"]] == ["eigene"]
    assert d["daytrip_value"] == "Ausflug"


def test_questions_endpoint_reports_errors_of_broken_user_file(client, tq):
    write(tq, {"steps": [{"key": "a", "title": "T", "label": "L", "type": "bogus"}]})
    tq.load(force=True)
    d = client.get("/api/trippilot/questions").get_json()
    assert d["source"] == "bundled" and d["errors"]
    assert len(d["steps"]) == len(BUNDLED["steps"])


def test_advisor_accepts_field_added_in_user_file(client, tq, monkeypatch):
    """Kernpunkt der Umstellung: eine in der JSON ergaenzte Frage landet auch im
    KI-Prompt statt beim Absenden still verworfen zu werden."""
    import ai_routes
    write(tq, {"daytrip_value": "Tagesausflug in der Nähe",
               "steps": [{"key": "haustier", "title": "Tier dabei?",
                          "label": "Haustier an Bord", "type": "single",
                          "options": ["Hund", "Katze"]}]})
    tq.load(force=True)
    assert ai_routes._advisor_fields() == ("haustier",)
    prompt = ai_routes._advisor_prompt({"haustier": "Katze"})
    assert "- Haustier an Bord: Katze" in prompt

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
                          'type': 'single', 'options': ['ja', 'nein', 'Ausflug']}]})
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


# ── Speichern (GUI-Editor) ─────────────────────────────────────────────────────

VALID = {'daytrip_value': 'Ausflug',
         'steps': [{'key': 'a', 'title': 'Frage?', 'label': 'Feld', 'type': 'single',
                    'options': ['ja', 'Ausflug']}]}


def test_save_writes_valid_document(tq):
    assert tq.save(VALID) == []
    with open(tq.QUESTIONS_PATH, encoding='utf-8') as f:
        assert json.load(f) == VALID
    assert tq.load()['source'] == 'user'


def test_save_creates_missing_directory(tq, tmp_path, monkeypatch):
    d = tmp_path / 'neu' / 'trippilot'
    monkeypatch.setattr(tq, 'QUESTIONS_DIR', str(d))
    monkeypatch.setattr(tq, 'QUESTIONS_PATH', str(d / 'questions.json'))
    assert tq.save(VALID) == []
    assert tq.user_exists() is True


def test_save_rejects_invalid_and_leaves_file_alone(tq):
    """Kernpunkt: was der Editor schreibt, kann den Wizard nie auf die
    Auslieferungsversion zurueckwerfen — ungueltiges wird gar nicht erst
    geschrieben."""
    tq.save(VALID)
    errors = tq.save({'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'bogus'}]})
    assert errors and any('type' in e for e in errors)
    with open(tq.QUESTIONS_PATH, encoding='utf-8') as f:
        assert json.load(f) == VALID


def test_save_rejects_value_that_is_no_option(tq):
    bad = json.loads(json.dumps(VALID))
    bad['daytrip_value'] = 'Gibt es nicht'
    assert tq.save(bad)
    assert tq.user_exists() is False


def test_save_invalidates_cache(tq):
    write(tq, VALID)
    assert [s['key'] for s in tq.load()['steps']] == ['a']
    other = {'steps': [{'key': 'b', 'title': 'T', 'label': 'L', 'type': 'text'}]}
    assert tq.save(other) == []
    # ohne Cache-Invalidierung stuende hier weiter 'a' — die mtime-Aufloesung
    # ist zu grob, um eine Aenderung in derselben Sekunde zu bemerken.
    assert [s['key'] for s in tq.load()['steps']] == ['b']


def test_save_leaves_no_temp_file(tq):
    import os
    tq.save(VALID)
    assert os.listdir(tq.QUESTIONS_DIR) == ['questions.json']


def test_save_keeps_unicode_readable(tq):
    """Emojis/Umlaute muessen im Klartext in der Datei stehen, damit die Datei
    auch im Texteditor bearbeitbar bleibt."""
    doc = {'steps': [{'key': 'a', 'title': 'Wohin?', 'label': 'Ziel', 'type': 'single',
                      'options': ['🌴 Strand', 'Gebäude']}]}
    assert tq.save(doc) == []
    with open(tq.QUESTIONS_PATH, encoding='utf-8') as f:
        raw = f.read()
    assert '🌴 Strand' in raw and 'Gebäude' in raw


def test_user_raw_returns_broken_but_parsable_document(tq):
    """Der Editor muss eine fehlerhafte Datei zeigen koennen — sonst wuerde ein
    Speichern die eigenen Fragen durch etwas anderes ersetzen."""
    broken = {'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'bogus'}]}
    write(tq, broken)
    assert tq.user_raw() == broken
    assert tq.validate(broken)


def test_user_raw_is_none_without_file_or_on_garbage(tq):
    assert tq.user_raw() is None
    with open(tq.QUESTIONS_PATH, 'w', encoding='utf-8') as f:
        f.write('{ kaputt')
    assert tq.user_raw() is None


def test_bundled_returns_shipped_document(tq):
    assert tq.bundled() == BUNDLED


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


def test_bundled_keeps_all_historically_known_fields():
    """Regression: die bis 0.89.x fest im Code stehenden Felder muessen weiter
    existieren — sonst laufen Prompt-Aufbau und Reise-DNA ins Leere. Neue Fragen
    duerfen dazukommen."""
    keys = {s['key'] for s in BUNDLED['steps']}
    assert keys >= {
        'region', 'excluded_countries', 'excluded_countries_other', 'interests',
        'beach_detail', 'berge_detail', 'travel_type', 'companions', 'budget',
        'duration', 'duration_daytrip', 'month', 'temp', 'water_type', 'sea', 'rain',
        'activities', 'accommodation', 'accommodation_size', 'hotel_wishes',
        'arrival_mode', 'home_location', 'max_distance', 'flight_time', 'airports',
        'dislikes', 'perfect_holiday', 'past_trips', 'perfect_daytrip'}
    types = {s['key']: s['type'] for s in BUNDLED['steps']}
    assert types['region'] == 'multi' and types['companions'] == 'single'
    assert types['home_location'] == 'text' and types['perfect_holiday'] == 'text'


# ── Semantik-Block (Reise-DNA / Prompt-Klauseln) ───────────────────────────────

def test_bundled_semantics_cover_every_dna_category():
    """Alle acht Kategorien der Reise-DNA-Tabelle brauchen Signale, sonst bleibt
    die Kategorie auf dem Sockelwert stehen."""
    dna = BUNDLED['semantics']['dna']
    assert set(dna) == {'🌴 Strand', '🏛️ Kultur', '🎉 Nachtleben', '⛰️ Aktiv',
                        '🍹 Entspannung', '🍽️ Kulinarik', '👨‍👩‍👧 Familie', '💰 Preisbewusst'}
    assert all(groups for groups in dna.values())


def test_bundled_semantics_values_are_real_options():
    """Kernpunkt: ein Semantik-Wert, den es als Option nicht gibt, wirkt nie."""
    options = {s['key']: s.get('options', []) for s in BUNDLED['steps']}
    sem = BUNDLED['semantics']
    all_options = {o for opts in options.values() for o in opts}
    for name in ('package_tour', 'self_arrival'):
        assert set(sem[name]) <= all_options, name
    for label, groups in sem['dna'].items():
        for key, vals in groups.items():
            assert set(vals) <= set(options[key]), f'{label}/{key}'


def test_bundled_daytrip_value_is_an_option():
    """Ohne exakte Übereinstimmung waere der Tagesausflug-Modus nicht auswaehlbar."""
    assert BUNDLED['daytrip_value'] in \
        {o for s in BUNDLED['steps'] for o in s.get('options', [])}


@pytest.mark.parametrize('sem,broken', [
    ({'package_tour': ['gibt es nicht']}, True),
    ({'self_arrival': ['gibt es nicht']}, True),
    ({'self_arrival': 'kein Array'}, True),
    ({'dna': {'Kategorie': {'unbekannter_key': ['x']}}}, True),
    ({'dna': {'Kategorie': {'a': ['gibt es nicht']}}}, True),
    ({'dna': {'Kategorie': {}}}, True),
    ({'package_tour': ['x'], 'dna': {'Kategorie': {'a': ['x']}}}, False),
])
def test_validate_checks_semantics(sem, broken):
    data = {'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'multi',
                       'options': ['x']}],
            'semantics': sem}
    assert bool(TQ.validate(data)) is broken


def test_validate_rejects_daytrip_value_that_is_no_option():
    data = {'daytrip_value': 'nicht vorhanden',
            'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'multi',
                       'options': ['x']}]}
    assert any('daytrip_value' in e for e in TQ.validate(data))


def test_validate_rejects_show_if_value_that_is_no_option():
    """Genau der Fehler, der bei einer halb durchgezogenen Umbenennung entsteht:
    die Frage wuerde stumm nie mehr erscheinen."""
    data = {'steps': [
        {'key': 'a', 'title': 'T', 'label': 'L', 'type': 'multi', 'options': ['x']},
        {'key': 'b', 'title': 'T', 'label': 'L', 'type': 'text',
         'show_if': {'key': 'a', 'contains': 'alter Name'}},
    ]}
    assert any('alter Name' in e for e in TQ.validate(data))


def test_semantics_returns_empty_dict_when_absent(tq):
    write(tq, {'steps': [{'key': 'a', 'title': 'T', 'label': 'L', 'type': 'text'}]})
    tq.load(force=True)
    assert tq.semantics() == {}


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
                          "type": "single", "options": ["ja", "Ausflug"]}]})
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
    write(tq, {"steps": [{"key": "haustier", "title": "Tier dabei?",
                          "label": "Haustier an Bord", "type": "single",
                          "options": ["Hund", "Katze"]}]})
    tq.load(force=True)
    assert ai_routes._advisor_fields() == ("haustier",)
    prompt = ai_routes._advisor_prompt({"haustier": "Katze"})
    assert "- Haustier an Bord: Katze" in prompt


def test_editor_endpoint_offers_bundled_when_no_user_file(client, tq):
    d = client.get("/api/trippilot/editor").get_json()
    assert d["source"] == "bundled" and d["errors"] == []
    assert d["data"] == BUNDLED and d["bundled"] == BUNDLED
    assert d["path"] == tq.QUESTIONS_PATH


def test_editor_endpoint_shows_user_file_with_its_errors(client, tq):
    """Nicht die Auslieferungsversion zeigen, sondern die kaputte eigene Datei —
    sonst repariert man im Editor etwas anderes, als auf der Platte liegt."""
    broken = {"steps": [{"key": "a", "title": "T", "label": "L", "type": "bogus"}]}
    write(tq, broken)
    d = client.get("/api/trippilot/editor").get_json()
    assert d["source"] == "user" and d["data"] == broken
    assert any("type" in e for e in d["errors"])


def test_editor_endpoint_flags_unparsable_user_file(client, tq):
    with open(tq.QUESTIONS_PATH, "w", encoding="utf-8") as f:
        f.write("{ kein JSON")
    d = client.get("/api/trippilot/editor").get_json()
    assert d["source"] == "bundled" and d["data"] == BUNDLED
    assert any("kein gültiges JSON" in e for e in d["errors"])


def test_editor_endpoint_saves_and_wizard_serves_it(client, tq):
    doc = {"daytrip_value": "Ausflug",
           "steps": [{"key": "eigene", "title": "Frage?", "label": "Feld",
                      "type": "single", "options": ["ja", "Ausflug"]}]}
    r = client.post("/api/trippilot/editor", json={"data": doc})
    assert r.status_code == 200 and r.get_json()["saved"] is True
    q = client.get("/api/trippilot/questions").get_json()
    assert q["source"] == "user" and [s["key"] for s in q["steps"]] == ["eigene"]


def test_editor_endpoint_rejects_invalid_document(client, tq):
    r = client.post("/api/trippilot/editor",
                    json={"data": {"steps": [{"key": "a", "title": "T", "label": "L",
                                              "type": "bogus"}]}})
    assert r.status_code == 400
    assert any("type" in e for e in r.get_json()["errors"])
    assert tq.user_exists() is False


def test_editor_endpoint_rejects_non_object(client, tq):
    r = client.post("/api/trippilot/editor", json={"data": [1, 2, 3]})
    assert r.status_code == 400 and r.get_json()["errors"]


def test_editor_endpoint_requires_auth(client, tq, monkeypatch):
    import app as A
    monkeypatch.setattr(A, "_auth_ok", lambda req: False)
    assert client.get("/api/trippilot/editor").status_code == 401
    assert client.post("/api/trippilot/editor", json={"data": BUNDLED}).status_code == 401
    assert tq.user_exists() is False


# ── Wirkung im Prompt/Scoring mit den ausgelieferten Fragen ────────────────────

@pytest.fixture
def bundled_ai(tq):
    """ai_routes gegen die ausgelieferte Fragen-Datei (keine Nutzerdatei)."""
    pytest.importorskip("flask")
    tq.load(force=True)
    import ai_routes
    return ai_routes


def _opt(key, needle):
    """Die eine Option von `key`, die `needle` enthaelt — nie abtippen."""
    step = next(s for s in BUNDLED['steps'] if s['key'] == key)
    hits = [o for o in step['options'] if needle in o]
    assert len(hits) == 1, f'{key}/{needle}: {hits}'
    return hits[0]


def test_daytrip_mode_triggers_with_bundled_value(bundled_ai):
    """Regression: mit Emoji-Praefix an der Option muss der Tagesausflug-Modus
    weiter anspringen (sonst greift der falsche Prompt)."""
    profile = {'region': [BUNDLED['daytrip_value']]}
    assert bundled_ai._is_daytrip(profile) is True
    assert bundled_ai._is_daytrip({'region': [_opt('region', 'Europa')]}) is False


def test_self_arrival_clause_in_prompt(bundled_ai):
    """Ohne diese Klausel schlaegt die KI Flugziele vor, obwohl Auto gewaehlt ist."""
    for needle in ('Auto', 'Bahn', 'Bus'):
        prompt = bundled_ai._advisor_prompt({'arrival_mode': _opt('arrival_mode', needle),
                                             'home_location': 'Köln'})
        assert 'reist eigenständig mit' in prompt, needle
    flug = bundled_ai._advisor_prompt({'arrival_mode': _opt('arrival_mode', 'Flugzeug')})
    assert 'reist eigenständig mit' not in flug


def test_package_tour_clause_in_prompt(bundled_ai):
    prompt = bundled_ai._advisor_prompt(
        {'travel_type': [_opt('travel_type', 'Pauschalreise')]})
    assert 'Pauschalreise (Flug + Hotel)' in prompt
    other = bundled_ai._advisor_prompt(
        {'travel_type': [_opt('travel_type', 'Kreuzfahrt')]})
    assert 'Pauschalreise (Flug + Hotel)' not in other


def test_dna_scores_react_to_bundled_answers(bundled_ai):
    """Alle acht Kategorien muessen mit den ausgelieferten Antwortwerten ueber
    den Sockelwert steigen koennen — sonst ist die Tabelle wertlos."""
    base = bundled_ai._advisor_dna_scores({})
    assert set(base.values()) == {15}
    for label, groups in BUNDLED['semantics']['dna'].items():
        profile = {key: list(vals) for key, vals in groups.items()}
        scores = bundled_ai._advisor_dna_scores(profile)
        assert scores[label] > 15, label
        assert scores[label] == min(100, 15 + 35 * len(groups)), label


def test_dna_counts_one_signal_per_question(bundled_ai):
    """Mehrere Treffer in derselben Frage zaehlen nur einmal."""
    groups = BUNDLED['semantics']['dna']['🌴 Strand']
    one = bundled_ai._advisor_dna_scores({'hotel_wishes': groups['hotel_wishes'][:1]})
    all_ = bundled_ai._advisor_dna_scores({'hotel_wishes': groups['hotel_wishes']})
    assert one['🌴 Strand'] == all_['🌴 Strand'] == 50

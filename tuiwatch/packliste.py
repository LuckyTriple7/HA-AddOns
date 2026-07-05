"""Default-Packliste-Vorlage (aus PDF-Vorlage übernommen) + Seed-Helfer."""

PACKING_TEMPLATE = {
    'Kleidung': ['T-Shirts / Tanks (5–7 Stück)', 'Shorts (2–3 Stück)', 'Badehosen (2–3 Stück)',
                 'Leichte lange Hose / Jeans', 'Abendliches Hemd / Poloshirt',
                 'Unterwäsche & Socken', 'Flip-Flops / Sandalen', 'Leichte Sneaker / Freizeitschuhe',
                 'Badesandalen', 'Leichter Hoodie / Sweatshirt'],
    'Strand & Meer': ['Strandtuch / Sarong', 'Strandtasche', 'Sonnencreme (LSF 30 & 50)',
                      'After-Sun Lotion', 'Sonnenbrille (UV-Schutz)', 'Sonnenhut / Cap',
                      'Schnorchelset (optional)', 'Luftmatratze / Strandspielzeug',
                      'Strandlektüre / E-Reader', 'Handtuchklammern'],
    'Körperpflege': ['Deo, Duschgel, Shampoo', 'Rasierer / Rasierschaum',
                      'Zahnbürste, Zahnpasta, Mundwasser', 'Lippenpflege mit LSF',
                      'Insektenschutz', 'Ohrstöpsel', 'Wattestäbchen', 'Parfüm',
                      'Taschentücher / Feuchttücher', 'Kamm / Haarbürste', 'Trimmer'],
    'Reiseapotheke': ['Schmerzmittel (Ibuprofen/Paracetamol)', 'Pflaster & Wundverband',
                       'Desinfektionsmittel', 'Magen-Darm-Mittel (z. B. Imodium)',
                       'Antihistaminikum (Allergie)', 'Augentropfen',
                       'Sonnen-/Wärmeblasen-Spray', 'Thermometer',
                       'Eigene Medikamente (Dauermedikation)'],
    'Technik & Dokumente': ['Reisepass / Personalausweis', 'Flugtickets (Ausdruck / App)',
                             'Hotelbestätigung', 'Krankenversicherungskarte / EHIC',
                             'Bargeld & Bankkarte', 'Smartphone & Ladekabel',
                             'Smartwatch & Ladegerät', 'Powerbank', 'Kopfhörer',
                             'Reiseadapter (Typ C/F)', 'Steckdosenleiste'],
    'Spiele & Unterhaltung': ['Kartenspiel (z. B. Mau-Mau, Poker)', 'UNO',
                              'Würfelspiel (z. B. Kniffel)', 'Reise-Brettspiel (Schach/Backgammon)',
                              'Strandspiele (Beachball, Paddel)', 'Wasserball', 'Rätsel-/Quizbuch'],
    'Sonstiges': ['Kleiner Tagesrucksack', 'Wasserflasche (wiederverwendbar)',
                  'Snacks für den Flug', 'Nackenkissen für den Flug', 'Schlafmaske',
                  'Wäschebeutel für Schmutzwäsche', 'Kleingeld (Trinkgeld)', 'Reisewaschmittel'],
}


def default_packing_rows(now_ts: int):
    """(category, label, checked=0, created)-Tupel für Bulk-Insert — Einfüge-
    reihenfolge (= spätere id-Reihenfolge) entspricht der Kategorie-/Item-
    Reihenfolge der Vorlage."""
    rows = []
    for cat, items in PACKING_TEMPLATE.items():
        for label in items:
            rows.append((cat, label, 0, now_ts))
    return rows

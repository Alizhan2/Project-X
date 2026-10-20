"""Geographic directory, NOT a timetable or a supplier station directory.

Internal IDs are deliberately separate from supplier IDs. Sources and maintenance:
see docs/kazakhstan.md. Names cover regional capitals and republican cities.
"""
CURRENCY = 'KZT'
TIMEZONE = 'Asia/Almaty'
MAX_JOURNEY_HOURS = 72


def names(en, ru, kk):
    return {'en': en, 'ru': ru, 'kk': kk}


_ROWS = [
    ('astana', names('Astana', 'Астана', 'Астана'), names('Astana city', 'город Астана', 'Астана қаласы')),
    ('almaty', names('Almaty', 'Алматы', 'Алматы'), names('Almaty city', 'город Алматы', 'Алматы қаласы')),
    ('shymkent', names('Shymkent', 'Шымкент', 'Шымкент'), names('Shymkent city', 'город Шымкент', 'Шымкент қаласы')),
    ('kokshetau', names('Kokshetau', 'Кокшетау', 'Көкшетау'), names('Akmola Region', 'Акмолинская область', 'Ақмола облысы')),
    ('aktobe', names('Aktobe', 'Актобе', 'Ақтөбе'), names('Aktobe Region', 'Актюбинская область', 'Ақтөбе облысы')),
    ('atyrau', names('Atyrau', 'Атырау', 'Атырау'), names('Atyrau Region', 'Атырауская область', 'Атырау облысы')),
    ('oral', names('Oral', 'Уральск', 'Орал'), names('West Kazakhstan Region', 'Западно-Казахстанская область', 'Батыс Қазақстан облысы')),
    ('aktau', names('Aktau', 'Актау', 'Ақтау'), names('Mangystau Region', 'Мангистауская область', 'Маңғыстау облысы')),
    ('kostanay', names('Kostanay', 'Костанай', 'Қостанай'), names('Kostanay Region', 'Костанайская область', 'Қостанай облысы')),
    ('petropavl', names('Petropavl', 'Петропавловск', 'Петропавл'), names('North Kazakhstan Region', 'Северо-Казахстанская область', 'Солтүстік Қазақстан облысы')),
    ('pavlodar', names('Pavlodar', 'Павлодар', 'Павлодар'), names('Pavlodar Region', 'Павлодарская область', 'Павлодар облысы')),
    ('karaganda', names('Karaganda', 'Караганда', 'Қарағанды'), names('Karaganda Region', 'Карагандинская область', 'Қарағанды облысы')),
    ('zhezkazgan', names('Zhezkazgan', 'Жезказган', 'Жезқазған'), names('Ulytau Region', 'область Улытау', 'Ұлытау облысы')),
    ('oskemen', names('Oskemen', 'Усть-Каменогорск', 'Өскемен'), names('East Kazakhstan Region', 'Восточно-Казахстанская область', 'Шығыс Қазақстан облысы')),
    ('semey', names('Semey', 'Семей', 'Семей'), names('Abai Region', 'область Абай', 'Абай облысы')),
    ('taldykorgan', names('Taldykorgan', 'Талдыкорган', 'Талдықорған'), names('Zhetysu Region', 'область Жетысу', 'Жетісу облысы')),
    ('konaev', names('Konaev', 'Конаев', 'Қонаев'), names('Almaty Region', 'Алматинская область', 'Алматы облысы')),
    ('taraz', names('Taraz', 'Тараз', 'Тараз'), names('Zhambyl Region', 'Жамбылская область', 'Жамбыл облысы')),
    ('kyzylorda', names('Kyzylorda', 'Кызылорда', 'Қызылорда'), names('Kyzylorda Region', 'Кызылординская область', 'Қызылорда облысы')),
    ('turkistan', names('Turkistan', 'Туркестан', 'Түркістан'), names('Turkistan Region', 'Туркестанская область', 'Түркістан облысы')),
]
CITIES = [{'id': 'kz-' + code, 'name': name, 'region': region, 'country': 'KZ', 'timezone': TIMEZONE}
          for code, name, region in _ROWS]
CITY_IDS = tuple(city['id'] for city in CITIES)

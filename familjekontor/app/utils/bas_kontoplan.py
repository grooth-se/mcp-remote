"""Swedish BAS Kontoplan - Standard Chart of Accounts.

Contains ~250 commonly used accounts from the BAS standard.
Used to seed accounts when creating a new company.
"""

# Format: (account_number, name, account_type)
# account_type: asset, liability, equity, revenue, expense

BAS_ACCOUNTS = [
    # 1 - Tillgångar (Assets)
    # 10 - Immateriella anläggningstillgångar
    ('1010', 'Balanserade utgifter för utvecklingsarbeten', 'asset'),
    ('1019', 'Ackumulerade avskrivningar balanserade utgifter', 'asset'),
    ('1030', 'Koncessioner', 'asset'),
    ('1050', 'Goodwill', 'asset'),
    ('1059', 'Ackumulerade avskrivningar goodwill', 'asset'),

    # 11 - Byggnader och mark
    ('1110', 'Byggnader', 'asset'),
    ('1119', 'Ackumulerade avskrivningar byggnader', 'asset'),
    ('1130', 'Mark', 'asset'),
    ('1150', 'Markanläggningar', 'asset'),

    # 12 - Maskiner och inventarier
    ('1210', 'Maskiner och andra tekniska anläggningar', 'asset'),
    ('1219', 'Ackumulerade avskrivningar maskiner', 'asset'),
    ('1220', 'Inventarier och verktyg', 'asset'),
    ('1229', 'Ackumulerade avskrivningar inventarier', 'asset'),
    ('1230', 'Installationer', 'asset'),
    ('1240', 'Bilar och andra transportmedel', 'asset'),
    ('1249', 'Ackumulerade avskrivningar bilar', 'asset'),
    ('1250', 'Datorer', 'asset'),
    ('1259', 'Ackumulerade avskrivningar datorer', 'asset'),

    # 13 - Finansiella anläggningstillgångar
    ('1310', 'Andelar i koncernföretag', 'asset'),
    ('1320', 'Långfristiga fordringar hos koncernföretag', 'asset'),
    ('1330', 'Andelar i intresseföretag', 'asset'),
    ('1340', 'Långfristiga fordringar hos intresseföretag', 'asset'),
    ('1350', 'Andra långfristiga värdepappersinnehav', 'asset'),
    ('1360', 'Andra långfristiga fordringar', 'asset'),
    ('1380', 'Andra finansiella anläggningstillgångar', 'asset'),

    # 14 - Lager, produkter i arbete
    ('1410', 'Lager av råvaror', 'asset'),
    ('1420', 'Lager av produkter i arbete', 'asset'),
    ('1430', 'Lager av färdiga varor', 'asset'),
    ('1440', 'Lager av handelsvaror', 'asset'),
    ('1460', 'Pågående arbeten', 'asset'),
    ('1470', 'Förskott till leverantörer', 'asset'),

    # 15 - Kundfordringar
    ('1510', 'Kundfordringar', 'asset'),
    ('1513', 'Kundfordringar - Loss allowance', 'asset'),
    ('1519', 'Nedskrivning av kundfordringar', 'asset'),

    # 16 - Övriga kortfristiga fordringar
    ('1610', 'Fordringar hos anställda', 'asset'),
    ('1620', 'Upparbetad men ej fakturerad intäkt', 'asset'),
    ('1630', 'Avräkning för skatter och avgifter', 'asset'),
    ('1640', 'Skattefordringar', 'asset'),
    ('1650', 'Momsfordran', 'asset'),
    ('1660', 'Kortfristiga fordringar hos koncernföretag', 'asset'),
    ('1680', 'Andra kortfristiga fordringar', 'asset'),
    ('1690', 'Fordringar hos andra', 'asset'),

    # 17 - Förutbetalda kostnader och upplupna intäkter
    ('1710', 'Förutbetalda hyror', 'asset'),
    ('1720', 'Förutbetalda leasingavgifter', 'asset'),
    ('1730', 'Förutbetalda försäkringspremier', 'asset'),
    ('1740', 'Förutbetalda räntekostnader', 'asset'),
    ('1750', 'Upplupna hyresintäkter', 'asset'),
    ('1760', 'Upplupna ränteintäkter', 'asset'),
    ('1790', 'Övriga förutbetalda kostnader och upplupna intäkter', 'asset'),

    # 18 - Kortfristiga placeringar
    ('1810', 'Andelar i börsnoterade företag', 'asset'),
    ('1820', 'Obligationer', 'asset'),
    ('1880', 'Andra kortfristiga placeringar', 'asset'),
    ('1890', 'Nedskrivning av kortfristiga placeringar', 'asset'),

    # 19 - Kassa och bank
    ('1910', 'Kassa', 'asset'),
    ('1920', 'PlusGiro', 'asset'),
    ('1930', 'Företagskonto/checkräkningskonto', 'asset'),
    ('1940', 'Övriga bankkonton', 'asset'),
    ('1950', 'Bankkonto i utländsk valuta', 'asset'),

    # 2 - Eget kapital och skulder (Equity & Liabilities)
    # 20 - Eget kapital
    ('2010', 'Eget kapital', 'equity'),
    ('2011', 'Aktiekapital', 'equity'),
    ('2012', 'Ej registrerat aktiekapital', 'equity'),
    ('2013', 'Överkursfond', 'equity'),
    ('2017', 'Årets resultat', 'equity'),
    ('2018', 'Eget kapital vid årets början', 'equity'),
    ('2019', 'Övriga fonder', 'equity'),
    ('2020', 'Eget kapital HB delägare 1', 'equity'),
    ('2030', 'Eget kapital HB delägare 2', 'equity'),
    ('2040', 'Eget kapital HB delägare 3', 'equity'),
    ('2060', 'Eget kapital i enskild firma', 'equity'),
    ('2070', 'Ackumulerade vinster/förluster', 'equity'),
    ('2080', 'Fond för utvecklingsutgifter', 'equity'),
    ('2090', 'Balanserad vinst eller förlust', 'equity'),
    ('2091', 'Balanserat resultat', 'equity'),
    ('2098', 'Vinst eller förlust från föregående år', 'equity'),
    ('2099', 'Årets resultat', 'equity'),

    # 21 - Obeskattade reserver
    ('2110', 'Periodiseringsfonder', 'liability'),
    ('2120', 'Periodiseringsfond tax 2020', 'liability'),
    ('2123', 'Periodiseringsfond tax 2023', 'liability'),
    ('2124', 'Periodiseringsfond tax 2024', 'liability'),
    ('2125', 'Periodiseringsfond tax 2025', 'liability'),
    ('2126', 'Periodiseringsfond tax 2026', 'liability'),
    ('2150', 'Ackumulerade överavskrivningar', 'liability'),

    # 22 - Avsättningar
    ('2210', 'Avsättningar för pensioner', 'liability'),
    ('2220', 'Avsättningar för skatter', 'liability'),
    ('2250', 'Övriga avsättningar', 'liability'),

    # 23 - Långfristiga skulder
    ('2310', 'Obligationslån', 'liability'),
    ('2320', 'Konvertibla lån', 'liability'),
    ('2330', 'Checkräkningskredit', 'liability'),
    ('2340', 'Byggnadskreditiv', 'liability'),
    ('2350', 'Skulder till kreditinstitut', 'liability'),
    ('2360', 'Skulder till koncernföretag', 'liability'),
    ('2390', 'Övriga långfristiga skulder', 'liability'),
    ('2393', 'Lån från delägare i HB', 'liability'),
    ('2395', 'Skulder till andra', 'liability'),

    # 24 - Kortfristiga skulder till kreditinstitut m.m.
    ('2410', 'Kortfristiga skulder till kreditinstitut', 'liability'),
    ('2417', 'Kortfristiga skulder till koncernföretag', 'liability'),
    ('2420', 'Förskott från kunder', 'liability'),
    ('2440', 'Leverantörsskulder', 'liability'),
    ('2450', 'Fakturerad men ej upparbetad intäkt', 'liability'),

    # 25 - Skatteskulder
    ('2510', 'Skatteskulder', 'liability'),
    ('2514', 'Beräknad inkomstskatt', 'liability'),

    # 26 - Moms och punktskatter
    ('2610', 'Utgående moms 25%', 'liability'),
    ('2620', 'Utgående moms 12%', 'liability'),
    ('2630', 'Utgående moms 6%', 'liability'),
    ('2640', 'Ingående moms', 'liability'),
    ('2641', 'Debiterad ingående moms', 'liability'),
    ('2645', 'Beräknad ingående moms på förvärv från utlandet', 'liability'),
    ('2650', 'Redovisningskonto för moms', 'liability'),

    # 27 - Personalens skatter, avgifter och löneavdrag
    ('2710', 'Personalens källskatt', 'liability'),
    ('2730', 'Arbetsgivaravgifter', 'liability'),
    ('2731', 'Avräkning lagstadgade sociala avgifter', 'liability'),
    ('2740', 'Nettolöner', 'liability'),
    ('2750', 'Utmätning av löner', 'liability'),
    ('2760', 'Fackföreningsavgifter', 'liability'),
    ('2790', 'Övriga löneavdrag', 'liability'),

    # 28 - Övriga kortfristiga skulder
    ('2810', 'Utdelning', 'liability'),
    ('2820', 'Koncernbidrag', 'liability'),
    ('2890', 'Övriga kortfristiga skulder', 'liability'),
    ('2895', 'Derivat', 'liability'),

    # 29 - Upplupna kostnader och förutbetalda intäkter
    ('2910', 'Upplupna löner', 'liability'),
    ('2920', 'Upplupna semesterlöner', 'liability'),
    ('2930', 'Upplupna arbetsgivaravgifter', 'liability'),
    ('2940', 'Upplupna räntekostnader', 'liability'),
    ('2950', 'Upplupna pensionskostnader', 'liability'),
    ('2960', 'Förutbetalda hyresintäkter', 'liability'),
    ('2970', 'Förutbetalda intäkter', 'liability'),
    ('2990', 'Övriga upplupna kostnader och förutbetalda intäkter', 'liability'),

    # 3 - Intäkter (Revenue)
    ('3000', 'Försäljning och utfört arbete', 'revenue'),
    ('3010', 'Försäljning varor', 'revenue'),
    ('3011', 'Försäljning varor 25% moms', 'revenue'),
    ('3012', 'Försäljning varor 12% moms', 'revenue'),
    ('3013', 'Försäljning varor 6% moms', 'revenue'),
    ('3014', 'Försäljning varor momsfri', 'revenue'),
    ('3040', 'Försäljning tjänster', 'revenue'),
    ('3041', 'Försäljning tjänster 25% moms', 'revenue'),
    ('3050', 'Försäljning tjänster utanför Sverige', 'revenue'),
    ('3051', 'Försäljning tjänster inom EU', 'revenue'),
    ('3052', 'Försäljning tjänster utanför EU', 'revenue'),
    ('3060', 'Försäljning varor utanför Sverige', 'revenue'),
    ('3100', 'Fakturerade kostnader', 'revenue'),
    ('3200', 'Försäljning anläggningstillgångar', 'revenue'),
    ('3300', 'Försäljning i utländsk valuta', 'revenue'),
    ('3500', 'Fakturerade frakter', 'revenue'),
    ('3590', 'Övriga sidointäkter', 'revenue'),
    ('3600', 'Rörelsebidrag', 'revenue'),
    ('3700', 'Lämnade rabatter', 'revenue'),
    ('3740', 'Öres- och kronutjämning', 'revenue'),
    ('3900', 'Övriga rörelseintäkter', 'revenue'),
    ('3910', 'Hyresintäkter', 'revenue'),
    ('3920', 'Provisionsintäkter', 'revenue'),
    ('3960', 'Valutakursvinster på fordringar/skulder av rörelsekaraktär', 'revenue'),
    ('3970', 'Vinst vid avyttring av immateriella/materiella anläggningstillgångar', 'revenue'),
    ('3980', 'Erhållna offentliga bidrag', 'revenue'),
    ('3990', 'Övriga ersättningar och intäkter', 'revenue'),

    # 4 - Kostnader för varor och material (Cost of goods)
    ('4000', 'Varuinköp/material', 'expense'),
    ('4010', 'Inköp varor och material', 'expense'),
    ('4100', 'Inköp varor inom EU', 'expense'),
    ('4200', 'Inköp varor utanför EU', 'expense'),
    ('4500', 'Övriga kostnadsposter', 'expense'),
    ('4510', 'Anställda underleverantörer', 'expense'),
    ('4530', 'Inhyrd personal', 'expense'),
    ('4600', 'Legoarbeten och underentreprenader', 'expense'),
    ('4700', 'Övriga inköp', 'expense'),
    ('4900', 'Förändring av lager', 'expense'),
    ('4910', 'Förändring av lager av råvaror', 'expense'),
    ('4960', 'Förändring av produkter i arbete', 'expense'),
    ('4990', 'Övrig lagerförändring', 'expense'),

    # 5 - Övriga externa kostnader (Other external expenses)
    ('5010', 'Lokalhyra', 'expense'),
    ('5020', 'El för lokal', 'expense'),
    ('5030', 'Värme', 'expense'),
    ('5040', 'Vatten och avlopp', 'expense'),
    ('5050', 'Lokalvård', 'expense'),
    ('5060', 'Övriga lokalkostnader', 'expense'),
    ('5090', 'Övriga lokalkostnader', 'expense'),
    ('5100', 'Fastighetskostnader', 'expense'),
    ('5110', 'Tomträttsavgäld/arrende', 'expense'),
    ('5120', 'Fastighetsförsäkring', 'expense'),
    ('5130', 'Fastighetsskatt/avgift', 'expense'),
    ('5200', 'Hyra av anläggningstillgångar', 'expense'),
    ('5210', 'Hyra av maskiner och inventarier', 'expense'),
    ('5250', 'Hyra av datorer', 'expense'),
    ('5300', 'Förbrukningsinventarier och förbrukningsmaterial', 'expense'),
    ('5400', 'Förbrukningsmaterial', 'expense'),
    ('5410', 'Förbrukningsinventarier', 'expense'),
    ('5420', 'Programvaror', 'expense'),
    ('5460', 'Förbrukningsmaterial', 'expense'),
    ('5500', 'Reparation och underhåll', 'expense'),
    ('5600', 'Transportkostnader', 'expense'),
    ('5610', 'Frakter', 'expense'),
    ('5700', 'Resekostnader', 'expense'),
    ('5710', 'Bilkostnader', 'expense'),
    ('5800', 'Resekostnader övrigt', 'expense'),
    ('5810', 'Biljetter', 'expense'),
    ('5820', 'Hotell', 'expense'),
    ('5830', 'Kost och logi', 'expense'),
    ('5900', 'Reklam och PR', 'expense'),
    ('5910', 'Annonsering', 'expense'),
    ('5920', 'Webbplats och internet', 'expense'),
    ('5930', 'Reklamtrycksaker', 'expense'),

    # 6 - Övriga externa kostnader (forts.)
    ('6000', 'Övriga försäljningskostnader', 'expense'),
    ('6010', 'Kontorsmaterial', 'expense'),
    ('6040', 'Facklitteratur', 'expense'),
    ('6050', 'Tele och post', 'expense'),
    ('6060', 'Telefon', 'expense'),
    ('6070', 'Mobiltelefon', 'expense'),
    ('6071', 'Internet', 'expense'),
    ('6100', 'Kontorsmaterial och trycksaker', 'expense'),
    ('6110', 'Kontorsmaterial', 'expense'),
    ('6150', 'Trycksaker', 'expense'),
    ('6200', 'Tele och post', 'expense'),
    ('6210', 'Telefon', 'expense'),
    ('6211', 'Mobiltelefon', 'expense'),
    ('6212', 'Datakom', 'expense'),
    ('6230', 'Porto', 'expense'),
    ('6250', 'Postbox', 'expense'),
    ('6300', 'Företagsförsäkringar', 'expense'),
    ('6310', 'Företagsförsäkringar', 'expense'),
    ('6350', 'Ansvarsförsäkring', 'expense'),
    ('6400', 'Förvaltningskostnader', 'expense'),
    ('6410', 'Styrelsearvoden', 'expense'),
    ('6420', 'Revisionsarvoden', 'expense'),
    ('6430', 'Management fee', 'expense'),
    ('6440', 'Juridisk rådgivning', 'expense'),
    ('6450', 'Redovisning/bokföring', 'expense'),
    ('6490', 'Övriga förvaltningskostnader', 'expense'),
    ('6500', 'Övriga externa tjänster', 'expense'),
    ('6510', 'Konsultarvoden', 'expense'),
    ('6520', 'Inhyrd personal', 'expense'),
    ('6530', 'IT-tjänster', 'expense'),
    ('6540', 'Utbildning', 'expense'),
    ('6550', 'Tillsynsavgifter', 'expense'),
    ('6560', 'Serviceavgifter', 'expense'),
    ('6570', 'Bankavgifter', 'expense'),
    ('6580', 'Advokat- och rättegångskostnader', 'expense'),
    ('6590', 'Övriga externa kostnader', 'expense'),
    ('6900', 'Övriga externa kostnader', 'expense'),
    ('6970', 'Tidningar och tidskrifter', 'expense'),
    ('6980', 'Föreningsavgifter', 'expense'),
    ('6990', 'Övriga kostnader', 'expense'),
    ('6991', 'Valutakursförluster rörelsekaraktär', 'expense'),
    ('6992', 'Ej avdragsgilla kostnader', 'expense'),

    # 7 - Personal (Personnel costs)
    ('7010', 'Löner till tjänstemän', 'expense'),
    ('7011', 'Löner till tjänstemän', 'expense'),
    ('7082', 'Sjuklöner', 'expense'),
    ('7090', 'Förändring av semesterlöneskuld', 'expense'),
    ('7200', 'Löner till kollektivanställda', 'expense'),
    ('7210', 'Löner till kollektivanställda', 'expense'),
    ('7220', 'Löner till kollektivanställda', 'expense'),
    ('7300', 'Kostnadsersättningar och naturaförmåner', 'expense'),
    ('7310', 'Traktamenten vid inrikes resor', 'expense'),
    ('7320', 'Traktamenten vid utrikes resor', 'expense'),
    ('7321', 'Skattefria traktamenten', 'expense'),
    ('7322', 'Skattepliktiga traktamenten', 'expense'),
    ('7330', 'Bilersättningar', 'expense'),
    ('7331', 'Skattefria bilersättningar', 'expense'),
    ('7332', 'Skattepliktiga bilersättningar', 'expense'),
    ('7380', 'Kostnader för förmåner till anställda', 'expense'),
    ('7381', 'Förmånsvärde', 'expense'),
    ('7382', 'Kostnader för personalförmåner', 'expense'),
    ('7385', 'Friskvård och hälsovård', 'expense'),
    ('7390', 'Övriga kostnadsersättningar och förmåner', 'expense'),
    ('7400', 'Pensionskostnader', 'expense'),
    ('7410', 'Pensionsförsäkringspremier', 'expense'),
    ('7411', 'Premiebefrielse', 'expense'),
    ('7412', 'ITP-premier', 'expense'),
    ('7420', 'Avsättning till pensioner', 'expense'),
    ('7490', 'Övriga pensionskostnader', 'expense'),
    ('7500', 'Sociala avgifter', 'expense'),
    ('7510', 'Arbetsgivaravgifter', 'expense'),
    ('7511', 'Arbetsgivaravgifter löner', 'expense'),
    ('7519', 'Arbetsgivaravgifter semester', 'expense'),
    ('7530', 'Löneskatt', 'expense'),
    ('7533', 'Särskild löneskatt pensionskostnader', 'expense'),
    ('7570', 'Premier för arbetsmarknadsförsäkringar', 'expense'),
    ('7580', 'Avgifter till Fora/Collectum', 'expense'),
    ('7600', 'Övriga personalkostnader', 'expense'),
    ('7610', 'Utbildningskostnader', 'expense'),
    ('7620', 'Sjuk- och hälsovård', 'expense'),
    ('7630', 'Personalrepresentation', 'expense'),
    ('7690', 'Övriga personalkostnader', 'expense'),

    # 7700-7899 - Nedskrivningar och avskrivningar
    ('7710', 'Nedskrivning av immateriella anläggningstillgångar', 'expense'),
    ('7720', 'Nedskrivning av byggnader och mark', 'expense'),
    ('7730', 'Nedskrivning av maskiner och inventarier', 'expense'),
    ('7810', 'Avskrivningar på immateriella anläggningstillgångar', 'expense'),
    ('7820', 'Avskrivningar på byggnader', 'expense'),
    ('7830', 'Avskrivningar på maskiner och inventarier', 'expense'),
    ('7831', 'Avskrivningar maskiner och tekniska anläggningar', 'expense'),
    ('7832', 'Avskrivningar inventarier och verktyg', 'expense'),
    ('7833', 'Avskrivningar installationer', 'expense'),
    ('7834', 'Avskrivningar bilar', 'expense'),
    ('7835', 'Avskrivningar datorer', 'expense'),

    # 8 - Finansiella poster (Financial items)
    ('8010', 'Resultat från andelar i koncernföretag', 'revenue'),
    ('8012', 'Utdelning från koncernföretag', 'revenue'),
    ('8020', 'Resultat från andelar i intresseföretag', 'revenue'),
    ('8030', 'Resultat vid försäljning av värdepapper', 'revenue'),
    ('8100', 'Ränteintäkter och liknande resultatposter', 'revenue'),
    ('8110', 'Ränteintäkter från bank', 'revenue'),
    ('8120', 'Ränteintäkter från koncernföretag', 'revenue'),
    ('8130', 'Ränteintäkter från intresseföretag', 'revenue'),
    ('8150', 'Ränteintäkter skattekonto', 'revenue'),
    ('8170', 'Övriga ränteintäkter', 'revenue'),
    ('8190', 'Övriga finansiella intäkter', 'revenue'),
    ('8200', 'Resultat från övriga värdepapper', 'revenue'),
    ('8210', 'Utdelning övriga värdepapper', 'revenue'),
    ('8220', 'Vinst vid försäljning av värdepapper', 'revenue'),
    ('8230', 'Förlust vid försäljning av värdepapper', 'expense'),
    ('8250', 'Orealiserade värdeförändringar', 'expense'),
    ('8270', 'Valutakursvinster finansiella poster', 'revenue'),
    ('8280', 'Valutakursförluster finansiella poster', 'expense'),
    ('8300', 'Räntekostnader och liknande resultatposter', 'expense'),
    ('8310', 'Räntekostnader lån', 'expense'),
    ('8311', 'Räntekostnader bank', 'expense'),
    ('8313', 'Räntekostnader koncernkonto', 'expense'),
    ('8314', 'Räntekostnader checkräkningskredit', 'expense'),
    ('8320', 'Räntekostnader till koncernföretag', 'expense'),
    ('8330', 'Räntekostnader till intresseföretag', 'expense'),
    ('8340', 'Räntekostnader leverantörsskulder', 'expense'),
    ('8370', 'Räntekostnader skattekonto', 'expense'),
    ('8390', 'Övriga räntekostnader', 'expense'),
    ('8400', 'Räntekostnader och liknande', 'expense'),
    ('8410', 'Bankavgifter', 'expense'),
    ('8490', 'Övriga finansiella kostnader', 'expense'),

    # Bokslutsdispositioner och skatt
    ('8810', 'Förändring av periodiseringsfonder', 'expense'),
    ('8820', 'Förändring av överavskrivningar', 'expense'),
    ('8830', 'Erhållna koncernbidrag', 'revenue'),
    ('8840', 'Lämnade koncernbidrag', 'expense'),
    ('8910', 'Skatt på årets resultat', 'expense'),
    ('8920', 'Skatt på årets resultat', 'expense'),
    ('8999', 'Årets resultat', 'equity'),
]


def seed_accounts_for_company(company_id):
    """Seed BAS accounts for a given company. Returns count of accounts created."""
    from app.extensions import db
    from app.models.accounting import Account

    existing = Account.query.filter_by(company_id=company_id).count()
    if existing > 0:
        return 0

    count = 0
    for number, name, account_type in BAS_ACCOUNTS:
        account = Account(
            company_id=company_id,
            account_number=number,
            name=name,
            account_type=account_type,
            active=True,
        )
        db.session.add(account)
        count += 1

    db.session.commit()
    return count

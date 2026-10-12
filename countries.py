"""The fleet's one country list: the 193 UN member states plus "Other".

THE RULE (owner's policy, fleet README §3): a country question offers exactly
the 193 member states of the United Nations
(https://www.un.org/en/about-us/member-states) and an "Other / not listed"
choice. Territories, dependencies, observer states and contested entries
(Taiwan, Hong Kong, Kosovo, Palestine, the Holy See, Western Sahara, ...) are
not offered; a participant from one of them chooses Other, and a tool that has
a free-text field behind Other stores what they type. The UN line is the
neutral one: the tools make no statehood judgement of their own. Membership
changes rarely (the last admission was South Sudan, 2011); a new member is one
row added to ``_MEMBERS`` and the test that counts 193 changed with it.

WHAT THE TOOLS HAD (checked 12 October 2026, FL-098 point 5). Six copies,
each offering exactly these 193 states, built three ways:

  * Drawbridge and Moral Mirror: pycountry 24.6.1 minus 56 non-member codes,
    17 "clean name" overrides, ISO alpha-2 STORED, "OTHER" for Other (the
    typed text replaces it in Moral Mirror). Drawbridge also has a 7-region
    roll-up keyed by code for its demographic chart.
  * Layoff (pycountry 23.12.11) and Polarity Profiler (pycountry 26.2.16):
    the same filter with 24 and 21 overrides, the English display NAME
    stored, "Other / not listed" for Other with typed text replacing it, a
    7-region roll-up keyed by name that also covers every non-member ISO
    entry plus Kosovo (answers stored before the UN-only switch), and in
    Layoff a name -> ISO numeric map for the world-atlas choropleth. PP shows
    German names from pycountry's gettext catalogue.
  * Inequality: a hand-typed list of ISO alpha-3 codes and names, alpha-3
    stored, "OTHER" with typed text kept in a separate column.
  * Whiteout: the Inequality names copied by hand, the name stored, a bare
    "Other" with no free text (deliberate minimisation, W28), and UN M49
    sub-regions for the educator's second breakdown, with Melanesia,
    Micronesia and Polynesia merged as "Pacific Islands".

Ten states carried different English names across the six lists (Brunei,
both Congos, Côte d'Ivoire, Cabo Verde, Czechia, Micronesia, the two Koreas,
Türkiye), Drawbridge's region table disagreed with Layoff's and PP's for
Azerbaijan, Pakistan, Greenland and Pitcairn, and PP showed eleven German
names in their formal ISO form ("Korea, Republik") next to clean English
ones ("South Korea").

WHY IT LOOKS AS IT DOES
  * One row per state with every code a tool stores or keys on: alpha-2,
    alpha-3 and the zero-padded numeric code (world-atlas feature ids).
  * ``name`` is the English name most of the six lists already used (a tie
    between three spellings of the Democratic Republic of the Congo went to
    the two tools that store codes, where a name change costs no data).
  * ``name_de`` is pycountry's German name in its short form, the same
    "clean name" rule the English column follows. No other tool shows German
    country names; Layoff shows the English names in all ten languages.
  * ``region`` is the 7-bucket roll-up of Drawbridge, Layoff and PP, with the
    two tools that agree outvoting the one that drifted. ``subregion`` is the
    UN M49 sub-region; ``subregion_of(..., merge_pacific=True)`` gives
    Whiteout's "Pacific Islands" bucket.
  * Every spelling a tool has stored is an alias, so ``lookup`` reads old
    rows: names from all six lists, pycountry's formal names, PP's former
    German labels, and the non-member entries (``NON_MEMBERS``, never
    offered) that Layoff's and PP's region maps still cover.
  * No pycountry at run time: the data is in this file, generated once from
    pycountry 26.2.16 and the six lists, and checked by tests.

Standard library only, no I/O, nothing at import beyond building the tables.
"""
from __future__ import annotations

import unicodedata
from typing import NamedTuple, Optional


class Country(NamedTuple):
    alpha2: str
    alpha3: str
    numeric: Optional[str]      # zero-padded ISO 3166-1 numeric; None for Kosovo
    name: str                   # English display name
    name_de: str                # German display name
    region: str                 # one of REGIONS
    subregion: Optional[str]    # UN M49 sub-region (members only)
    member: bool                # a UN member state, offered in the list


OTHER_CODE = "OTHER"
OTHER_LABEL = "Other / not listed"
OTHER_LABEL_DE = "Andere / nicht aufgeführt"

#: The 7-bucket roll-up, in the order the charts show it.
REGIONS = (
    "Africa", "Asia-Pacific", "Europe", "Latin America",
    "Middle East / Central Asia", "North America", "Other",
)

#: UN M49 sub-regions that hold at least one member state.
SUBREGIONS = (
    "Northern Africa", "Sub-Saharan Africa", "Northern America",
    "Latin America and the Caribbean", "Central Asia", "Eastern Asia",
    "South-eastern Asia", "Southern Asia", "Western Asia", "Eastern Europe",
    "Northern Europe", "Southern Europe", "Western Europe",
    "Australia and New Zealand", "Melanesia", "Micronesia", "Polynesia",
)
PACIFIC_ISLANDS = "Pacific Islands"
_PACIFIC = frozenset({"Melanesia", "Micronesia", "Polynesia"})

LANGUAGES = ("en", "de")

# (alpha-2, alpha-3, numeric, English, German, region, M49 sub-region)
_MEMBERS = (
    ('AD', 'AND', '020', 'Andorra', 'Andorra', 'Europe', 'Southern Europe'),
    ('AE', 'ARE', '784', 'United Arab Emirates', 'Vereinigte Arabische Emirate', 'Middle East / Central Asia', 'Western Asia'),
    ('AF', 'AFG', '004', 'Afghanistan', 'Afghanistan', 'Middle East / Central Asia', 'Southern Asia'),
    ('AG', 'ATG', '028', 'Antigua and Barbuda', 'Antigua und Barbuda', 'Latin America', 'Latin America and the Caribbean'),
    ('AL', 'ALB', '008', 'Albania', 'Albanien', 'Europe', 'Southern Europe'),
    ('AM', 'ARM', '051', 'Armenia', 'Armenien', 'Europe', 'Western Asia'),
    ('AO', 'AGO', '024', 'Angola', 'Angola', 'Africa', 'Sub-Saharan Africa'),
    ('AR', 'ARG', '032', 'Argentina', 'Argentinien', 'Latin America', 'Latin America and the Caribbean'),
    ('AT', 'AUT', '040', 'Austria', 'Österreich', 'Europe', 'Western Europe'),
    ('AU', 'AUS', '036', 'Australia', 'Australien', 'Asia-Pacific', 'Australia and New Zealand'),
    ('AZ', 'AZE', '031', 'Azerbaijan', 'Aserbaidschan', 'Europe', 'Western Asia'),
    ('BA', 'BIH', '070', 'Bosnia and Herzegovina', 'Bosnien und Herzegowina', 'Europe', 'Southern Europe'),
    ('BB', 'BRB', '052', 'Barbados', 'Barbados', 'Latin America', 'Latin America and the Caribbean'),
    ('BD', 'BGD', '050', 'Bangladesh', 'Bangladesch', 'Asia-Pacific', 'Southern Asia'),
    ('BE', 'BEL', '056', 'Belgium', 'Belgien', 'Europe', 'Western Europe'),
    ('BF', 'BFA', '854', 'Burkina Faso', 'Burkina Faso', 'Africa', 'Sub-Saharan Africa'),
    ('BG', 'BGR', '100', 'Bulgaria', 'Bulgarien', 'Europe', 'Eastern Europe'),
    ('BH', 'BHR', '048', 'Bahrain', 'Bahrain', 'Middle East / Central Asia', 'Western Asia'),
    ('BI', 'BDI', '108', 'Burundi', 'Burundi', 'Africa', 'Sub-Saharan Africa'),
    ('BJ', 'BEN', '204', 'Benin', 'Benin', 'Africa', 'Sub-Saharan Africa'),
    ('BN', 'BRN', '096', 'Brunei Darussalam', 'Brunei Darussalam', 'Asia-Pacific', 'South-eastern Asia'),
    ('BO', 'BOL', '068', 'Bolivia', 'Bolivien', 'Latin America', 'Latin America and the Caribbean'),
    ('BR', 'BRA', '076', 'Brazil', 'Brasilien', 'Latin America', 'Latin America and the Caribbean'),
    ('BS', 'BHS', '044', 'Bahamas', 'Bahamas', 'Latin America', 'Latin America and the Caribbean'),
    ('BT', 'BTN', '064', 'Bhutan', 'Bhutan', 'Asia-Pacific', 'Southern Asia'),
    ('BW', 'BWA', '072', 'Botswana', 'Botsuana', 'Africa', 'Sub-Saharan Africa'),
    ('BY', 'BLR', '112', 'Belarus', 'Belarus', 'Europe', 'Eastern Europe'),
    ('BZ', 'BLZ', '084', 'Belize', 'Belize', 'Latin America', 'Latin America and the Caribbean'),
    ('CA', 'CAN', '124', 'Canada', 'Kanada', 'North America', 'Northern America'),
    ('CD', 'COD', '180', 'Democratic Republic of the Congo', 'Demokratische Republik Kongo', 'Africa', 'Sub-Saharan Africa'),
    ('CF', 'CAF', '140', 'Central African Republic', 'Zentralafrikanische Republik', 'Africa', 'Sub-Saharan Africa'),
    ('CG', 'COG', '178', 'Congo', 'Kongo', 'Africa', 'Sub-Saharan Africa'),
    ('CH', 'CHE', '756', 'Switzerland', 'Schweiz', 'Europe', 'Western Europe'),
    ('CI', 'CIV', '384', "Côte d'Ivoire", "Côte d'Ivoire", 'Africa', 'Sub-Saharan Africa'),
    ('CL', 'CHL', '152', 'Chile', 'Chile', 'Latin America', 'Latin America and the Caribbean'),
    ('CM', 'CMR', '120', 'Cameroon', 'Kamerun', 'Africa', 'Sub-Saharan Africa'),
    ('CN', 'CHN', '156', 'China', 'China', 'Asia-Pacific', 'Eastern Asia'),
    ('CO', 'COL', '170', 'Colombia', 'Kolumbien', 'Latin America', 'Latin America and the Caribbean'),
    ('CR', 'CRI', '188', 'Costa Rica', 'Costa Rica', 'Latin America', 'Latin America and the Caribbean'),
    ('CU', 'CUB', '192', 'Cuba', 'Kuba', 'Latin America', 'Latin America and the Caribbean'),
    ('CV', 'CPV', '132', 'Cabo Verde', 'Kap Verde', 'Africa', 'Sub-Saharan Africa'),
    ('CY', 'CYP', '196', 'Cyprus', 'Zypern', 'Europe', 'Western Asia'),
    ('CZ', 'CZE', '203', 'Czech Republic', 'Tschechien', 'Europe', 'Eastern Europe'),
    ('DE', 'DEU', '276', 'Germany', 'Deutschland', 'Europe', 'Western Europe'),
    ('DJ', 'DJI', '262', 'Djibouti', 'Dschibuti', 'Africa', 'Sub-Saharan Africa'),
    ('DK', 'DNK', '208', 'Denmark', 'Dänemark', 'Europe', 'Northern Europe'),
    ('DM', 'DMA', '212', 'Dominica', 'Dominica', 'Latin America', 'Latin America and the Caribbean'),
    ('DO', 'DOM', '214', 'Dominican Republic', 'Dominikanische Republik', 'Latin America', 'Latin America and the Caribbean'),
    ('DZ', 'DZA', '012', 'Algeria', 'Algerien', 'Africa', 'Northern Africa'),
    ('EC', 'ECU', '218', 'Ecuador', 'Ecuador', 'Latin America', 'Latin America and the Caribbean'),
    ('EE', 'EST', '233', 'Estonia', 'Estland', 'Europe', 'Northern Europe'),
    ('EG', 'EGY', '818', 'Egypt', 'Ägypten', 'Africa', 'Northern Africa'),
    ('ER', 'ERI', '232', 'Eritrea', 'Eritrea', 'Africa', 'Sub-Saharan Africa'),
    ('ES', 'ESP', '724', 'Spain', 'Spanien', 'Europe', 'Southern Europe'),
    ('ET', 'ETH', '231', 'Ethiopia', 'Äthiopien', 'Africa', 'Sub-Saharan Africa'),
    ('FI', 'FIN', '246', 'Finland', 'Finnland', 'Europe', 'Northern Europe'),
    ('FJ', 'FJI', '242', 'Fiji', 'Fidschi', 'Asia-Pacific', 'Melanesia'),
    ('FM', 'FSM', '583', 'Micronesia', 'Mikronesien', 'Asia-Pacific', 'Micronesia'),
    ('FR', 'FRA', '250', 'France', 'Frankreich', 'Europe', 'Western Europe'),
    ('GA', 'GAB', '266', 'Gabon', 'Gabun', 'Africa', 'Sub-Saharan Africa'),
    ('GB', 'GBR', '826', 'United Kingdom', 'Vereinigtes Königreich', 'Europe', 'Northern Europe'),
    ('GD', 'GRD', '308', 'Grenada', 'Grenada', 'Latin America', 'Latin America and the Caribbean'),
    ('GE', 'GEO', '268', 'Georgia', 'Georgien', 'Europe', 'Western Asia'),
    ('GH', 'GHA', '288', 'Ghana', 'Ghana', 'Africa', 'Sub-Saharan Africa'),
    ('GM', 'GMB', '270', 'Gambia', 'Gambia', 'Africa', 'Sub-Saharan Africa'),
    ('GN', 'GIN', '324', 'Guinea', 'Guinea', 'Africa', 'Sub-Saharan Africa'),
    ('GQ', 'GNQ', '226', 'Equatorial Guinea', 'Äquatorialguinea', 'Africa', 'Sub-Saharan Africa'),
    ('GR', 'GRC', '300', 'Greece', 'Griechenland', 'Europe', 'Southern Europe'),
    ('GT', 'GTM', '320', 'Guatemala', 'Guatemala', 'Latin America', 'Latin America and the Caribbean'),
    ('GW', 'GNB', '624', 'Guinea-Bissau', 'Guinea-Bissau', 'Africa', 'Sub-Saharan Africa'),
    ('GY', 'GUY', '328', 'Guyana', 'Guyana', 'Latin America', 'Latin America and the Caribbean'),
    ('HN', 'HND', '340', 'Honduras', 'Honduras', 'Latin America', 'Latin America and the Caribbean'),
    ('HR', 'HRV', '191', 'Croatia', 'Kroatien', 'Europe', 'Southern Europe'),
    ('HT', 'HTI', '332', 'Haiti', 'Haiti', 'Latin America', 'Latin America and the Caribbean'),
    ('HU', 'HUN', '348', 'Hungary', 'Ungarn', 'Europe', 'Eastern Europe'),
    ('ID', 'IDN', '360', 'Indonesia', 'Indonesien', 'Asia-Pacific', 'South-eastern Asia'),
    ('IE', 'IRL', '372', 'Ireland', 'Irland', 'Europe', 'Northern Europe'),
    ('IL', 'ISR', '376', 'Israel', 'Israel', 'Middle East / Central Asia', 'Western Asia'),
    ('IN', 'IND', '356', 'India', 'Indien', 'Asia-Pacific', 'Southern Asia'),
    ('IQ', 'IRQ', '368', 'Iraq', 'Irak', 'Middle East / Central Asia', 'Western Asia'),
    ('IR', 'IRN', '364', 'Iran', 'Iran', 'Middle East / Central Asia', 'Southern Asia'),
    ('IS', 'ISL', '352', 'Iceland', 'Island', 'Europe', 'Northern Europe'),
    ('IT', 'ITA', '380', 'Italy', 'Italien', 'Europe', 'Southern Europe'),
    ('JM', 'JAM', '388', 'Jamaica', 'Jamaika', 'Latin America', 'Latin America and the Caribbean'),
    ('JO', 'JOR', '400', 'Jordan', 'Jordanien', 'Middle East / Central Asia', 'Western Asia'),
    ('JP', 'JPN', '392', 'Japan', 'Japan', 'Asia-Pacific', 'Eastern Asia'),
    ('KE', 'KEN', '404', 'Kenya', 'Kenia', 'Africa', 'Sub-Saharan Africa'),
    ('KG', 'KGZ', '417', 'Kyrgyzstan', 'Kirgisistan', 'Middle East / Central Asia', 'Central Asia'),
    ('KH', 'KHM', '116', 'Cambodia', 'Kambodscha', 'Asia-Pacific', 'South-eastern Asia'),
    ('KI', 'KIR', '296', 'Kiribati', 'Kiribati', 'Asia-Pacific', 'Micronesia'),
    ('KM', 'COM', '174', 'Comoros', 'Komoren', 'Africa', 'Sub-Saharan Africa'),
    ('KN', 'KNA', '659', 'Saint Kitts and Nevis', 'St. Kitts und Nevis', 'Latin America', 'Latin America and the Caribbean'),
    ('KP', 'PRK', '408', 'North Korea', 'Nordkorea', 'Asia-Pacific', 'Eastern Asia'),
    ('KR', 'KOR', '410', 'South Korea', 'Südkorea', 'Asia-Pacific', 'Eastern Asia'),
    ('KW', 'KWT', '414', 'Kuwait', 'Kuwait', 'Middle East / Central Asia', 'Western Asia'),
    ('KZ', 'KAZ', '398', 'Kazakhstan', 'Kasachstan', 'Middle East / Central Asia', 'Central Asia'),
    ('LA', 'LAO', '418', 'Laos', 'Laos', 'Asia-Pacific', 'South-eastern Asia'),
    ('LB', 'LBN', '422', 'Lebanon', 'Libanon', 'Middle East / Central Asia', 'Western Asia'),
    ('LC', 'LCA', '662', 'Saint Lucia', 'St. Lucia', 'Latin America', 'Latin America and the Caribbean'),
    ('LI', 'LIE', '438', 'Liechtenstein', 'Liechtenstein', 'Europe', 'Western Europe'),
    ('LK', 'LKA', '144', 'Sri Lanka', 'Sri Lanka', 'Asia-Pacific', 'Southern Asia'),
    ('LR', 'LBR', '430', 'Liberia', 'Liberia', 'Africa', 'Sub-Saharan Africa'),
    ('LS', 'LSO', '426', 'Lesotho', 'Lesotho', 'Africa', 'Sub-Saharan Africa'),
    ('LT', 'LTU', '440', 'Lithuania', 'Litauen', 'Europe', 'Northern Europe'),
    ('LU', 'LUX', '442', 'Luxembourg', 'Luxemburg', 'Europe', 'Western Europe'),
    ('LV', 'LVA', '428', 'Latvia', 'Lettland', 'Europe', 'Northern Europe'),
    ('LY', 'LBY', '434', 'Libya', 'Libyen', 'Africa', 'Northern Africa'),
    ('MA', 'MAR', '504', 'Morocco', 'Marokko', 'Africa', 'Northern Africa'),
    ('MC', 'MCO', '492', 'Monaco', 'Monaco', 'Europe', 'Western Europe'),
    ('MD', 'MDA', '498', 'Moldova', 'Moldau', 'Europe', 'Eastern Europe'),
    ('ME', 'MNE', '499', 'Montenegro', 'Montenegro', 'Europe', 'Southern Europe'),
    ('MG', 'MDG', '450', 'Madagascar', 'Madagaskar', 'Africa', 'Sub-Saharan Africa'),
    ('MH', 'MHL', '584', 'Marshall Islands', 'Marshallinseln', 'Asia-Pacific', 'Micronesia'),
    ('MK', 'MKD', '807', 'North Macedonia', 'Nordmazedonien', 'Europe', 'Southern Europe'),
    ('ML', 'MLI', '466', 'Mali', 'Mali', 'Africa', 'Sub-Saharan Africa'),
    ('MM', 'MMR', '104', 'Myanmar', 'Myanmar', 'Asia-Pacific', 'South-eastern Asia'),
    ('MN', 'MNG', '496', 'Mongolia', 'Mongolei', 'Asia-Pacific', 'Eastern Asia'),
    ('MR', 'MRT', '478', 'Mauritania', 'Mauretanien', 'Africa', 'Sub-Saharan Africa'),
    ('MT', 'MLT', '470', 'Malta', 'Malta', 'Europe', 'Southern Europe'),
    ('MU', 'MUS', '480', 'Mauritius', 'Mauritius', 'Africa', 'Sub-Saharan Africa'),
    ('MV', 'MDV', '462', 'Maldives', 'Malediven', 'Asia-Pacific', 'Southern Asia'),
    ('MW', 'MWI', '454', 'Malawi', 'Malawi', 'Africa', 'Sub-Saharan Africa'),
    ('MX', 'MEX', '484', 'Mexico', 'Mexiko', 'Latin America', 'Latin America and the Caribbean'),
    ('MY', 'MYS', '458', 'Malaysia', 'Malaysia', 'Asia-Pacific', 'South-eastern Asia'),
    ('MZ', 'MOZ', '508', 'Mozambique', 'Mosambik', 'Africa', 'Sub-Saharan Africa'),
    ('NA', 'NAM', '516', 'Namibia', 'Namibia', 'Africa', 'Sub-Saharan Africa'),
    ('NE', 'NER', '562', 'Niger', 'Niger', 'Africa', 'Sub-Saharan Africa'),
    ('NG', 'NGA', '566', 'Nigeria', 'Nigeria', 'Africa', 'Sub-Saharan Africa'),
    ('NI', 'NIC', '558', 'Nicaragua', 'Nicaragua', 'Latin America', 'Latin America and the Caribbean'),
    ('NL', 'NLD', '528', 'Netherlands', 'Niederlande', 'Europe', 'Western Europe'),
    ('NO', 'NOR', '578', 'Norway', 'Norwegen', 'Europe', 'Northern Europe'),
    ('NP', 'NPL', '524', 'Nepal', 'Nepal', 'Asia-Pacific', 'Southern Asia'),
    ('NR', 'NRU', '520', 'Nauru', 'Nauru', 'Asia-Pacific', 'Micronesia'),
    ('NZ', 'NZL', '554', 'New Zealand', 'Neuseeland', 'Asia-Pacific', 'Australia and New Zealand'),
    ('OM', 'OMN', '512', 'Oman', 'Oman', 'Middle East / Central Asia', 'Western Asia'),
    ('PA', 'PAN', '591', 'Panama', 'Panama', 'Latin America', 'Latin America and the Caribbean'),
    ('PE', 'PER', '604', 'Peru', 'Peru', 'Latin America', 'Latin America and the Caribbean'),
    ('PG', 'PNG', '598', 'Papua New Guinea', 'Papua-Neuguinea', 'Asia-Pacific', 'Melanesia'),
    ('PH', 'PHL', '608', 'Philippines', 'Philippinen', 'Asia-Pacific', 'South-eastern Asia'),
    ('PK', 'PAK', '586', 'Pakistan', 'Pakistan', 'Asia-Pacific', 'Southern Asia'),
    ('PL', 'POL', '616', 'Poland', 'Polen', 'Europe', 'Eastern Europe'),
    ('PT', 'PRT', '620', 'Portugal', 'Portugal', 'Europe', 'Southern Europe'),
    ('PW', 'PLW', '585', 'Palau', 'Palau', 'Asia-Pacific', 'Micronesia'),
    ('PY', 'PRY', '600', 'Paraguay', 'Paraguay', 'Latin America', 'Latin America and the Caribbean'),
    ('QA', 'QAT', '634', 'Qatar', 'Katar', 'Middle East / Central Asia', 'Western Asia'),
    ('RO', 'ROU', '642', 'Romania', 'Rumänien', 'Europe', 'Eastern Europe'),
    ('RS', 'SRB', '688', 'Serbia', 'Serbien', 'Europe', 'Southern Europe'),
    ('RU', 'RUS', '643', 'Russia', 'Russland', 'Europe', 'Eastern Europe'),
    ('RW', 'RWA', '646', 'Rwanda', 'Ruanda', 'Africa', 'Sub-Saharan Africa'),
    ('SA', 'SAU', '682', 'Saudi Arabia', 'Saudi-Arabien', 'Middle East / Central Asia', 'Western Asia'),
    ('SB', 'SLB', '090', 'Solomon Islands', 'Salomoninseln', 'Asia-Pacific', 'Melanesia'),
    ('SC', 'SYC', '690', 'Seychelles', 'Seychellen', 'Africa', 'Sub-Saharan Africa'),
    ('SD', 'SDN', '729', 'Sudan', 'Sudan', 'Africa', 'Northern Africa'),
    ('SE', 'SWE', '752', 'Sweden', 'Schweden', 'Europe', 'Northern Europe'),
    ('SG', 'SGP', '702', 'Singapore', 'Singapur', 'Asia-Pacific', 'South-eastern Asia'),
    ('SI', 'SVN', '705', 'Slovenia', 'Slowenien', 'Europe', 'Southern Europe'),
    ('SK', 'SVK', '703', 'Slovakia', 'Slowakei', 'Europe', 'Eastern Europe'),
    ('SL', 'SLE', '694', 'Sierra Leone', 'Sierra Leone', 'Africa', 'Sub-Saharan Africa'),
    ('SM', 'SMR', '674', 'San Marino', 'San Marino', 'Europe', 'Southern Europe'),
    ('SN', 'SEN', '686', 'Senegal', 'Senegal', 'Africa', 'Sub-Saharan Africa'),
    ('SO', 'SOM', '706', 'Somalia', 'Somalia', 'Africa', 'Sub-Saharan Africa'),
    ('SR', 'SUR', '740', 'Suriname', 'Suriname', 'Latin America', 'Latin America and the Caribbean'),
    ('SS', 'SSD', '728', 'South Sudan', 'Südsudan', 'Africa', 'Sub-Saharan Africa'),
    ('ST', 'STP', '678', 'Sao Tome and Principe', 'São Tomé und Príncipe', 'Africa', 'Sub-Saharan Africa'),
    ('SV', 'SLV', '222', 'El Salvador', 'El Salvador', 'Latin America', 'Latin America and the Caribbean'),
    ('SY', 'SYR', '760', 'Syria', 'Syrien', 'Middle East / Central Asia', 'Western Asia'),
    ('SZ', 'SWZ', '748', 'Eswatini', 'Eswatini', 'Africa', 'Sub-Saharan Africa'),
    ('TD', 'TCD', '148', 'Chad', 'Tschad', 'Africa', 'Sub-Saharan Africa'),
    ('TG', 'TGO', '768', 'Togo', 'Togo', 'Africa', 'Sub-Saharan Africa'),
    ('TH', 'THA', '764', 'Thailand', 'Thailand', 'Asia-Pacific', 'South-eastern Asia'),
    ('TJ', 'TJK', '762', 'Tajikistan', 'Tadschikistan', 'Middle East / Central Asia', 'Central Asia'),
    ('TL', 'TLS', '626', 'Timor-Leste', 'Timor-Leste', 'Asia-Pacific', 'South-eastern Asia'),
    ('TM', 'TKM', '795', 'Turkmenistan', 'Turkmenistan', 'Middle East / Central Asia', 'Central Asia'),
    ('TN', 'TUN', '788', 'Tunisia', 'Tunesien', 'Africa', 'Northern Africa'),
    ('TO', 'TON', '776', 'Tonga', 'Tonga', 'Asia-Pacific', 'Polynesia'),
    ('TR', 'TUR', '792', 'Türkiye', 'Türkei', 'Middle East / Central Asia', 'Western Asia'),
    ('TT', 'TTO', '780', 'Trinidad and Tobago', 'Trinidad und Tobago', 'Latin America', 'Latin America and the Caribbean'),
    ('TV', 'TUV', '798', 'Tuvalu', 'Tuvalu', 'Asia-Pacific', 'Polynesia'),
    ('TZ', 'TZA', '834', 'Tanzania', 'Tansania', 'Africa', 'Sub-Saharan Africa'),
    ('UA', 'UKR', '804', 'Ukraine', 'Ukraine', 'Europe', 'Eastern Europe'),
    ('UG', 'UGA', '800', 'Uganda', 'Uganda', 'Africa', 'Sub-Saharan Africa'),
    ('US', 'USA', '840', 'United States', 'Vereinigte Staaten', 'North America', 'Northern America'),
    ('UY', 'URY', '858', 'Uruguay', 'Uruguay', 'Latin America', 'Latin America and the Caribbean'),
    ('UZ', 'UZB', '860', 'Uzbekistan', 'Usbekistan', 'Middle East / Central Asia', 'Central Asia'),
    ('VC', 'VCT', '670', 'Saint Vincent and the Grenadines', 'St. Vincent und die Grenadinen', 'Latin America', 'Latin America and the Caribbean'),
    ('VE', 'VEN', '862', 'Venezuela', 'Venezuela', 'Latin America', 'Latin America and the Caribbean'),
    ('VN', 'VNM', '704', 'Vietnam', 'Vietnam', 'Asia-Pacific', 'South-eastern Asia'),
    ('VU', 'VUT', '548', 'Vanuatu', 'Vanuatu', 'Asia-Pacific', 'Melanesia'),
    ('WS', 'WSM', '882', 'Samoa', 'Samoa', 'Asia-Pacific', 'Polynesia'),
    ('YE', 'YEM', '887', 'Yemen', 'Jemen', 'Middle East / Central Asia', 'Western Asia'),
    ('ZA', 'ZAF', '710', 'South Africa', 'Südafrika', 'Africa', 'Sub-Saharan Africa'),
    ('ZM', 'ZMB', '894', 'Zambia', 'Sambia', 'Africa', 'Sub-Saharan Africa'),
    ('ZW', 'ZWE', '716', 'Zimbabwe', 'Simbabwe', 'Africa', 'Sub-Saharan Africa'),
)

_ALIASES = {
    'BN': ('Brunei',),
    'BO': ('Bolivia, Plurinational State of', 'Bolivien, Plurinationaler Staat'),
    'CD': ('Congo (Democratic Republic)', 'Congo, The Democratic Republic of the', 'DR Congo'),
    'CG': ('Republic of Congo',),
    'CI': ("Cote d'Ivoire",),
    'CV': ('Cape Verde',),
    'CZ': ('Czechia',),
    'FM': ('Micronesia, Federated States of', 'Mikronesien, Föderierte Staaten von'),
    'IR': ('Iran, Islamic Republic of', 'Iran, Islamische Republik'),
    'KP': ('Korea (North)', "Korea, Democratic People's Republic of", 'Korea, Demokratische Volksrepublik'),
    'KR': ('Korea (South)', 'Korea, Republic of', 'Korea, Republik'),
    'LA': ("Lao People's Democratic Republic", 'Laos, Demokratische Volksrepublik'),
    'MD': ('Moldau, Republik', 'Moldova, Republic of'),
    'RU': ('Russian Federation', 'Russische Föderation'),
    'SY': ('Syrian Arab Republic', 'Syrien, Arabische Republik'),
    'TR': ('Turkey',),
    'TZ': ('Tansania, Vereinigte Republik', 'Tanzania, United Republic of'),
    'VE': ('Venezuela, Bolivarian Republic of', 'Venezuela, Bolivarische Republik'),
    'VN': ('Viet Nam',),
}

_NON_MEMBERS = (
    ('AI', 'AIA', '660', 'Anguilla', 'Latin America', ()),
    ('AQ', 'ATA', '010', 'Antarctica', 'Other', ()),
    ('AS', 'ASM', '016', 'American Samoa', 'Asia-Pacific', ()),
    ('AW', 'ABW', '533', 'Aruba', 'Latin America', ()),
    ('AX', 'ALA', '248', 'Åland Islands', 'Europe', ()),
    ('BL', 'BLM', '652', 'Saint Barthélemy', 'Latin America', ()),
    ('BM', 'BMU', '060', 'Bermuda', 'North America', ()),
    ('BQ', 'BES', '535', 'Bonaire, Sint Eustatius and Saba', 'Latin America', ()),
    ('BV', 'BVT', '074', 'Bouvet Island', 'Other', ()),
    ('CC', 'CCK', '166', 'Cocos (Keeling) Islands', 'Asia-Pacific', ()),
    ('CK', 'COK', '184', 'Cook Islands', 'Asia-Pacific', ()),
    ('CW', 'CUW', '531', 'Curaçao', 'Latin America', ()),
    ('CX', 'CXR', '162', 'Christmas Island', 'Asia-Pacific', ()),
    ('EH', 'ESH', '732', 'Western Sahara', 'Africa', ()),
    ('FK', 'FLK', '238', 'Falkland Islands (Malvinas)', 'Latin America', ()),
    ('FO', 'FRO', '234', 'Faroe Islands', 'Europe', ()),
    ('GF', 'GUF', '254', 'French Guiana', 'Latin America', ()),
    ('GG', 'GGY', '831', 'Guernsey', 'Europe', ()),
    ('GI', 'GIB', '292', 'Gibraltar', 'Europe', ()),
    ('GL', 'GRL', '304', 'Greenland', 'North America', ()),
    ('GP', 'GLP', '312', 'Guadeloupe', 'Latin America', ()),
    ('GS', 'SGS', '239', 'South Georgia and the South Sandwich Islands', 'Other', ()),
    ('GU', 'GUM', '316', 'Guam', 'Asia-Pacific', ()),
    ('HK', 'HKG', '344', 'Hong Kong', 'Asia-Pacific', ()),
    ('HM', 'HMD', '334', 'Heard Island and McDonald Islands', 'Other', ()),
    ('IM', 'IMN', '833', 'Isle of Man', 'Europe', ()),
    ('IO', 'IOT', '086', 'British Indian Ocean Territory', 'Other', ()),
    ('JE', 'JEY', '832', 'Jersey', 'Europe', ()),
    ('KY', 'CYM', '136', 'Cayman Islands', 'Latin America', ()),
    ('MF', 'MAF', '663', 'Saint Martin (French part)', 'Latin America', ()),
    ('MO', 'MAC', '446', 'Macao', 'Asia-Pacific', ()),
    ('MP', 'MNP', '580', 'Northern Mariana Islands', 'Asia-Pacific', ()),
    ('MQ', 'MTQ', '474', 'Martinique', 'Latin America', ()),
    ('MS', 'MSR', '500', 'Montserrat', 'Latin America', ()),
    ('NC', 'NCL', '540', 'New Caledonia', 'Asia-Pacific', ()),
    ('NF', 'NFK', '574', 'Norfolk Island', 'Asia-Pacific', ()),
    ('NU', 'NIU', '570', 'Niue', 'Asia-Pacific', ()),
    ('PF', 'PYF', '258', 'French Polynesia', 'Asia-Pacific', ()),
    ('PM', 'SPM', '666', 'Saint Pierre and Miquelon', 'North America', ()),
    ('PN', 'PCN', '612', 'Pitcairn', 'Asia-Pacific', ()),
    ('PR', 'PRI', '630', 'Puerto Rico', 'Latin America', ()),
    ('PS', 'PSE', '275', 'Palestinian Territories', 'Middle East / Central Asia', ('Palestine, State of',)),
    ('RE', 'REU', '638', 'Réunion', 'Africa', ()),
    ('SH', 'SHN', '654', 'Saint Helena, Ascension and Tristan da Cunha', 'Africa', ()),
    ('SJ', 'SJM', '744', 'Svalbard and Jan Mayen', 'Europe', ()),
    ('SX', 'SXM', '534', 'Sint Maarten (Dutch part)', 'Latin America', ()),
    ('TC', 'TCA', '796', 'Turks and Caicos Islands', 'Latin America', ()),
    ('TF', 'ATF', '260', 'French Southern Territories', 'Other', ()),
    ('TK', 'TKL', '772', 'Tokelau', 'Asia-Pacific', ()),
    ('TW', 'TWN', '158', 'Taiwan', 'Asia-Pacific', ('Taiwan, Province of China',)),
    ('UM', 'UMI', '581', 'United States Minor Outlying Islands', 'Other', ()),
    ('VA', 'VAT', '336', 'Holy See (Vatican City State)', 'Europe', ()),
    ('VG', 'VGB', '092', 'Virgin Islands, British', 'Latin America', ()),
    ('VI', 'VIR', '850', 'Virgin Islands, U.S.', 'Latin America', ()),
    ('WF', 'WLF', '876', 'Wallis and Futuna', 'Asia-Pacific', ()),
    ('XK', 'XKX', None, 'Kosovo', 'Europe', ()),
    ('YT', 'MYT', '175', 'Mayotte', 'Africa', ()),
)


def _member(row: tuple) -> Country:
    return Country(*row, member=True)


def _non_member(row: tuple) -> Country:
    a2, a3, num, name, region, _aliases = row
    return Country(a2, a3, num, name, name, region, None, member=False)


def sort_key(label: str) -> str:
    """Alphabetical order a reader expects: accents and case ignored.

    Plain ``casefold`` put "Ägypten" and "Österreich" after "Zypern"."""
    decomposed = unicodedata.normalize("NFKD", label)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


#: The 193 UN member states, in English alphabetical order.
MEMBERS: tuple = tuple(sorted((_member(r) for r in _MEMBERS), key=lambda c: sort_key(c.name)))

#: ISO entries that are NOT members, plus Kosovo. Never offered; kept so an
#: answer stored before the UN-only lists (or typed under Other) still finds
#: its region and map code.
NON_MEMBERS: tuple = tuple(_non_member(r) for r in _NON_MEMBERS)


def _build_indexes():
    codes: dict = {}
    names: dict = {}

    def add_name(label: str, country: Country) -> None:
        key = label.casefold()
        if names.get(key, country) is not country:
            raise ValueError("country name %r names two entries" % label)
        names[key] = country

    for c in MEMBERS + NON_MEMBERS:
        for code in (c.alpha2, c.alpha3, c.numeric):
            if code:
                if code in codes:
                    raise ValueError("country code %r used twice" % code)
                codes[code] = c
        add_name(c.name, c)
        add_name(c.name_de, c)
    # The English spellings a name column may hold, for stored_names().
    spellings = [(c.name, c) for c in MEMBERS + NON_MEMBERS]
    for a2, aliases in _ALIASES.items():
        for label in aliases:
            add_name(label, codes[a2])
            spellings.append((label, codes[a2]))
    for row in _NON_MEMBERS:
        for label in row[5]:
            add_name(label, codes[row[0]])
            spellings.append((label, codes[row[0]]))
    return codes, names, spellings


_BY_CODE, _BY_NAME, _SPELLINGS = _build_indexes()


def lookup(value) -> Optional[Country]:
    """The entry a stored value names, member or not; None if none does.

    Codes match exactly (alpha-2 and alpha-3 in capitals, numeric as digits,
    zero-padded here), so a typed "in" under Other is not read as India.
    Names match without regard to case: the English and German names and
    every spelling a fleet tool has stored."""
    if value is None:
        return None
    if isinstance(value, int):
        value = "%03d" % value
    value = str(value).strip()
    if not value:
        return None
    if value.isdigit():
        value = value.zfill(3)
    found = _BY_CODE.get(value)
    if found is not None:
        return found
    return _BY_NAME.get(value.casefold())


def member(value) -> Optional[Country]:
    """Like ``lookup``, but only a UN member state."""
    found = lookup(value)
    return found if found is not None and found.member else None


def is_member(value) -> bool:
    return member(value) is not None


def name_of(value, lang: str = "en") -> Optional[str]:
    """Display name in ``lang`` (German for "de", English for every other
    language, as Layoff shows them today); None if ``value`` names nothing."""
    found = lookup(value)
    if found is None:
        return None
    return found.name_de if lang == "de" else found.name


def region_of(value, default: Optional[str] = "Other") -> Optional[str]:
    """The 7-bucket region for a stored value.

    Empty -> None (nothing answered). Other, a typed answer that names no
    entry, or an unknown code -> ``default``: "Other" is what Drawbridge,
    Layoff and PP show. A typed answer that names a non-member ("Taiwan")
    gets that entry's region, as Layoff's and PP's maps did."""
    if value is None or not str(value).strip():
        return None
    found = lookup(value)
    return found.region if found is not None else default


def subregion_of(value, *, merge_pacific: bool = False,
                 default: Optional[str] = None) -> Optional[str]:
    """The UN M49 sub-region of a member state; ``default`` for anything
    else (Other, free text, a non-member). Whiteout passes
    ``merge_pacific=True`` and ``default="Not stated"``."""
    found = member(value) if value is not None else None
    if found is None:
        return default
    if merge_pacific and found.subregion in _PACIFIC:
        return PACIFIC_ISLANDS
    return found.subregion


def stored_names(region: str) -> list:
    """Every spelling a name-storing tool may hold for ``region``, sorted.

    For a SQL ``IN (...)`` over a column that stores names: PP's class
    filter expands a region to the names in it. Old spellings and non-member
    entries are included, and "Other / not listed" for the region "Other",
    as PP's map did."""
    names = {label for label, c in _SPELLINGS if c.region == region}
    if region == "Other":
        names.add(OTHER_LABEL)
    return sorted(names)


_VALUE_FIELDS = ("alpha2", "alpha3", "name")


def options(lang: str = "en", *, value: str = "alpha2",
            other: bool = True) -> list:
    """[(stored value, label), ...] for a country select, Other last.

    ``value`` is what the tool stores: "alpha2" (Drawbridge, Moral Mirror),
    "alpha3" (Inequality) or "name", the English name (Layoff, PP,
    Whiteout), which stays English whatever the page language, so aggregates
    read the same across languages. Labels are in ``lang`` and sorted for a
    reader of it. Other's value is OTHER_CODE for a code and OTHER_LABEL for
    a name. A tool with its own Other wording (Whiteout's bare "Other")
    passes ``other=False`` and appends its own entry.
    """
    if value not in _VALUE_FIELDS:
        raise ValueError("value must be one of %s" % ", ".join(_VALUE_FIELDS))
    pairs = [(getattr(c, value), c.name_de if lang == "de" else c.name)
             for c in MEMBERS]
    pairs.sort(key=lambda p: sort_key(p[1]))
    if other:
        stored = OTHER_LABEL if value == "name" else OTHER_CODE
        pairs.append((stored, OTHER_LABEL_DE if lang == "de" else OTHER_LABEL))
    return pairs

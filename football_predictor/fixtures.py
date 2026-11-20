"""Weekend fixtures and the bookmaker 1X2 odds (home, draw, away) supplied by the user.

Team names follow model.norm(): no trailing "FC"/"AFC".
"""

# Share of the final probability taken from the de-margined bookmaker odds.
# The odds reflect current form, injuries and the table; the model's data is
# stale (PL/CH/LaLiga end 2026-09-20; LaLiga 2 ends 2025-11-03, nothing from 2026-27;
# Serie A ends 2026-09-20, Serie B ends 2026-03-17;
# Bundesliga ends 2026-09-20, 2. Bundesliga ends 2025-11-02;
# Ligue 1 ends 2026-09-20, Ligue 2 ends 2025-11-03;
# Eredivisie ends 2026-09-20, no Eerste Divisie data;
# Belgian Pro League ends 2025-11-02, nothing from 2026-27. League One/Two end 2025-12-29), so lean on the market.
MARKET_WEIGHT = {"PL": 0.7, "CH": 0.7, "L1": 0.85, "LL": 0.7, "LL2": 0.9, "SA": 0.7, "BL": 0.7, "FR": 0.7, "NL": 0.7, "BE": 0.85}

FIXTURES = {
    "PL": [  # 21-22 Nov 2026
        {"when": "Sat 13:30", "home": "Manchester City", "away": "Fulham", "odds": (1.42, 5.20, 7.00)},
        {"when": "Sat 16:00", "home": "Tottenham Hotspur", "away": "Ipswich Town", "odds": (1.55, 4.50, 5.60)},
        {"when": "Sat 16:00", "home": "Chelsea", "away": "Leeds United", "odds": (1.92, 3.70, 4.00)},
        {"when": "Sat 16:00", "home": "Aston Villa", "away": "Sunderland", "odds": (1.78, 3.85, 4.50)},
        {"when": "Sat 16:00", "home": "Coventry City", "away": "Crystal Palace", "odds": (2.53, 3.55, 2.74)},
        {"when": "Sat 16:00", "home": "AFC Bournemouth", "away": "Nottingham Forest", "odds": (1.98, 3.60, 3.85)},
        {"when": "Sat 18:30", "home": "Newcastle United", "away": "Arsenal", "odds": (5.60, 4.30, 1.58)},
        {"when": "Sun 15:00", "home": "Hull City", "away": "Brighton & Hove Albion", "odds": (6.10, 4.50, 1.52)},
        {"when": "Sun 17:30", "home": "Liverpool", "away": "Manchester United", "odds": (1.78, 4.20, 4.10)},
    ],
    "CH": [  # Sat 21 Nov 2026
        {"when": "Sat 13:30", "home": "Millwall", "away": "Queens Park Rangers", "odds": (2.60, 3.35, 2.64)},
        {"when": "Sat 13:30", "home": "Southampton", "away": "Derby County", "odds": (1.38, 5.00, 7.30)},
        {"when": "Sat 13:30", "home": "Norwich City", "away": "Cardiff City", "odds": (1.77, 4.15, 4.00)},
        {"when": "Sat 16:00", "home": "Lincoln City", "away": "Wrexham", "odds": (2.90, 2.98, 2.64)},
        {"when": "Sat 16:00", "home": "Middlesbrough", "away": "Bristol City", "odds": (1.38, 5.00, 7.10)},
        {"when": "Sat 16:00", "home": "West Ham United", "away": "Preston North End", "odds": (1.19, 7.20, 11.25)},
        {"when": "Sat 16:00", "home": "Bolton Wanderers", "away": "Portsmouth", "odds": (2.80, 3.25, 2.52)},
        {"when": "Sat 16:00", "home": "Sheffield United", "away": "Watford", "odds": (1.58, 4.05, 5.40)},
        {"when": "Sat 16:00", "home": "Swansea City", "away": "West Bromwich Albion", "odds": (2.60, 3.20, 2.77)},
        {"when": "Sat 16:00", "home": "Stoke City", "away": "Birmingham City", "odds": (2.95, 3.10, 2.50)},
        {"when": "Sat 16:00", "home": "Wolverhampton Wanderers", "away": "Charlton Athletic", "odds": (1.33, 5.20, 8.40)},
    ],
    "L1": [  # Fri 20 - Sat 21 Nov 2026
        {"when": "Fri 21:00", "home": "Barnsley", "away": "Sheffield Wednesday", "odds": (3.00, 3.65, 2.16)},
        {"when": "Sat 13:30", "home": "Reading", "away": "Bromley", "odds": (1.37, 5.00, 7.00)},
        {"when": "Sat 13:30", "home": "Blackpool", "away": "Wigan Athletic", "odds": (2.13, 3.30, 3.35)},
        {"when": "Sat 16:00", "home": "Mansfield Town", "away": "Milton Keynes Dons", "odds": (2.56, 3.30, 2.64)},
        {"when": "Sat 16:00", "home": "Burton Albion", "away": "Luton Town", "odds": (4.65, 3.80, 1.68)},
        {"when": "Sat 16:00", "home": "Notts County", "away": "Stevenage", "odds": (2.28, 3.15, 3.20)},
        {"when": "Sat 16:00", "home": "Leyton Orient", "away": "AFC Wimbledon", "odds": (1.76, 3.75, 4.25)},
        {"when": "Sat 16:00", "home": "Plymouth Argyle", "away": "Peterborough United", "odds": (1.80, 3.90, 3.90)},
        {"when": "Sat 16:00", "home": "Huddersfield Town", "away": "Leicester City", "odds": (2.02, 3.50, 3.45)},
        {"when": "Sat 16:00", "home": "Cambridge United", "away": "Stockport County", "odds": (3.70, 3.80, 1.86)},
        {"when": "Sat 16:00", "home": "Bradford City", "away": "Doncaster Rovers", "odds": (1.66, 3.80, 4.90)},
        {"when": "Sat 16:00", "home": "Oxford United", "away": "Wycombe Wanderers", "odds": (2.38, 3.30, 2.87)},
    ],
    "LL": [  # Fri 20 - Sun 22 Nov 2026 (Monday's games were not in the paste)
        {"when": "Fri 21:00", "home": "Athletic Club", "away": "RCD Espanyol de Barcelona", "odds": (1.52, 4.45, 6.00)},
        {"when": "Sat 14:00", "home": "Deportivo Alavés", "away": "Deportivo La Coruña", "odds": (2.26, 3.25, 3.30)},
        {"when": "Sat 16:15", "home": "Rayo Vallecano de Madrid", "away": "Valencia CF", "odds": (1.95, 3.50, 4.00)},
        {"when": "Sat 18:30", "home": "Sevilla", "away": "Real Betis Balompié", "odds": (2.93, 3.40, 2.42)},
        {"when": "Sat 21:00", "home": "Real Madrid CF", "away": "RC Celta de Vigo", "odds": (1.16, 8.00, 15.00)},
        {"when": "Sun 14:00", "home": "FC Barcelona", "away": "Villarreal CF", "odds": (1.23, 7.10, 10.25)},
        {"when": "Sun 16:15", "home": "Racing Santander", "away": "Real Sociedad de Fútbol", "odds": (3.15, 4.10, 2.04)},
        {"when": "Sun 18:30", "home": "CA Osasuna", "away": "Málaga CF", "odds": (1.84, 3.55, 4.40)},
        {"when": "Sun 21:00", "home": "Getafe CF", "away": "Club Atlético de Madrid", "odds": (5.90, 3.90, 1.60)},
    ],
    "LL2": [  # Fri 20 - Mon 23 Nov 2026
        {"when": "Fri 20:30", "home": "FC Andorra", "away": "CD Leganés", "odds": (1.85, 3.60, 4.10)},
        {"when": "Sat 14:00", "home": "CE Sabadell", "away": "Granada CF", "odds": (2.46, 3.10, 3.00)},
        {"when": "Sat 16:15", "home": "Real Sociedad B", "away": "Cádiz CF", "odds": (1.96, 3.55, 3.75)},
        {"when": "Sat 18:30", "home": "CD Castellón", "away": "CD Eldense", "odds": (1.42, 4.90, 6.70)},
        {"when": "Sat 21:00", "home": "CD Tenerife", "away": "RCD Mallorca", "odds": (3.35, 3.25, 2.20)},
        {"when": "Sun 14:00", "home": "Córdoba CF", "away": "Real Oviedo", "odds": (1.92, 3.75, 3.65)},
        {"when": "Sun 16:15", "home": "Sporting Gijón", "away": "UD Las Palmas", "odds": (2.12, 3.40, 3.40)},
        {"when": "Sun 18:30", "home": "RC Celta de Vigo B", "away": "Real Valladolid", "odds": (3.30, 3.60, 2.08)},
        {"when": "Sun 18:30", "home": "Girona", "away": "SD Eibar", "odds": (1.80, 3.75, 4.25)},
        {"when": "Sun 21:00", "home": "Burgos CF", "away": "Albacete", "odds": (2.05, 3.30, 3.70)},
        {"when": "Mon 20:30", "home": "AD Ceuta", "away": "UD Almería", "odds": (3.40, 3.85, 1.97)},
    ],
    "SA": [  # Sat 21 - Sun 22 Nov 2026
        {"when": "Sat 15:00", "home": "Como 1907", "away": "Cagliari Calcio", "odds": (1.30, 5.70, 8.90)},
        {"when": "Sat 15:00", "home": "SS Lazio", "away": "US Lecce", "odds": (1.42, 4.80, 7.20)},
        {"when": "Sat 18:00", "home": "Parma Calcio 1913", "away": "AS Roma", "odds": (9.50, 5.60, 1.30)},
        {"when": "Sat 20:45", "home": "SSC Napoli", "away": "Torino", "odds": (1.50, 4.50, 6.20)},
        {"when": "Sun 12:30", "home": "Juventus", "away": "Venezia", "odds": (1.38, 5.00, 7.70)},
        {"when": "Sun 15:00", "home": "Sassuolo Calcio", "away": "Genoa CFC", "odds": (2.75, 3.35, 2.57)},
        {"when": "Sun 15:00", "home": "Bologna FC 1909", "away": "Udinese Calcio", "odds": (1.75, 3.75, 4.80)},
        {"when": "Sun 18:00", "home": "AC Milan", "away": "Frosinone Calcio", "odds": (1.55, 4.70, 5.20)},
        {"when": "Sun 20:45", "home": "Atalanta BC", "away": "FC Internazionale Milano", "odds": (4.90, 4.50, 1.60)},
    ],
    "BL": [  # Fri 20 - Sun 22 Nov 2026
        {"when": "Fri 20:30", "home": "FC Bayern München", "away": "1. FC Köln", "odds": (1.08, 12.00, 22.00)},
        {"when": "Sat 15:30", "home": "SV 07 Elversberg", "away": "SC Freiburg", "odds": (3.50, 3.75, 2.00)},
        {"when": "Sat 15:30", "home": "Borussia Mönchengladbach", "away": "Borussia Dortmund", "odds": (4.95, 4.40, 1.62)},
        {"when": "Sat 15:30", "home": "Bayer 04 Leverkusen", "away": "SC Paderborn 07", "odds": (1.32, 5.80, 8.30)},
        {"when": "Sat 15:30", "home": "1. FC Union Berlin", "away": "RB Leipzig", "odds": (5.60, 4.75, 1.52)},
        {"when": "Sat 15:30", "home": "Eintracht Frankfurt", "away": "TSG 1899 Hoffenheim", "odds": (2.42, 3.90, 2.63)},
        {"when": "Sat 18:30", "home": "FC Schalke 04", "away": "VfB Stuttgart", "odds": (3.90, 4.05, 1.83)},
        {"when": "Sun 15:30", "home": "FC Augsburg", "away": "1. FSV Mainz 05", "odds": (2.65, 3.85, 2.42)},
        {"when": "Sun 17:30", "home": "SV Werder Bremen", "away": "Hamburger SV", "odds": (1.68, 4.25, 4.50)},
    ],
    "FR": [  # Fri 20 - Sun 22 Nov 2026 (key "FR" because "L1" is League One)
        {"when": "Fri 20:45", "home": "ES Troyes AC", "away": "Le Havre AC", "odds": (2.26, 3.40, 3.20)},
        {"when": "Sat 17:15", "home": "OGC Nice", "away": "Paris Saint-Germain", "odds": (5.80, 5.05, 1.47)},
        {"when": "Sat 20:45", "home": "RC Strasbourg Alsace", "away": "Stade Brestois 29", "odds": (2.28, 3.65, 2.97)},
        {"when": "Sat 20:45", "home": "Racing Club de Lens", "away": "Toulouse", "odds": (1.90, 3.90, 3.75)},
        {"when": "Sat 20:45", "home": "Lille OSC", "away": "Olympique Lyonnais", "odds": (2.30, 3.25, 3.25)},
        {"when": "Sat 20:45", "home": "AS Monaco", "away": "AJ Auxerre", "odds": (1.42, 5.05, 6.70)},
        {"when": "Sun 15:00", "home": "Paris", "away": "Angers SCO", "odds": (1.36, 5.20, 8.40)},
        {"when": "Sun 17:15", "home": "FC Lorient", "away": "Stade Rennais FC 1901", "odds": (2.82, 3.40, 2.50)},
        {"when": "Sun 20:45", "home": "Olympique de Marseille", "away": "Le Mans", "odds": (1.48, 4.80, 5.90)},
    ],
    "NL": [  # Sat 21 - Sun 22 Nov 2026
        {"when": "Sat 16:30", "home": "NEC", "away": "PSV", "odds": (4.00, 4.50, 1.73)},
        {"when": "Sat 18:45", "home": "FC Utrecht", "away": "SC Cambuur-Leeuwarden", "odds": (1.92, 4.10, 3.55)},
        {"when": "Sat 18:45", "home": "Feyenoord Rotterdam", "away": "SBV Excelsior", "odds": (1.23, 7.10, 10.50)},
        {"when": "Sat 21:00", "home": "Telstar 1963", "away": "PEC Zwolle", "odds": (2.07, 3.65, 3.40)},
        {"when": "Sat 21:00", "home": "FC Groningen", "away": "SC Heerenveen", "odds": (2.53, 3.75, 2.57)},
        {"when": "Sun 12:15", "home": "FC Twente '65", "away": "Willem II Tilburg", "odds": (1.08, 12.75, 20.00)},
        {"when": "Sun 14:30", "home": "AFC Ajax", "away": "ADO Den Haag", "odds": (1.19, 7.80, 12.25)},
        {"when": "Sun 14:30", "home": "Sparta Rotterdam", "away": "AZ", "odds": (4.20, 4.25, 1.74)},
        {"when": "Sun 16:45", "home": "Go Ahead Eagles", "away": "Fortuna Sittard", "odds": (1.64, 4.40, 4.75)},
    ],
    "BE": [  # Fri 20 - Sun 22 Nov 2026
        {"when": "Fri 20:45", "home": "Cercle Brugge", "away": "KVC Westerlo", "odds": (2.02, 3.75, 3.35)},
        {"when": "Sat 16:00", "home": "Sporting Charleroi", "away": "Sint-Truidense VV", "odds": (2.02, 3.70, 3.35)},
        {"when": "Sat 18:15", "home": "KRC Genk", "away": "RAAL La Louviére", "odds": (1.46, 4.75, 6.20)},
        {"when": "Sat 20:45", "home": "KV Mechelen", "away": "Club Brugge KV", "odds": (6.40, 5.15, 1.40)},
        {"when": "Sat 20:45", "home": "SV Zulte Waregem", "away": "Royal Antwerp", "odds": (2.20, 3.50, 3.10)},
        {"when": "Sun 13:30", "home": "Waasland-Beveren", "away": "KAA Gent", "odds": (3.55, 3.50, 2.02)},
        {"when": "Sun 16:00", "home": "KV Kortrijk", "away": "Union Saint-Gilloise", "odds": (7.20, 4.90, 1.40)},
        {"when": "Sun 18:30", "home": "RSC Anderlecht", "away": "Oud-Heverlee Leuven", "odds": (1.47, 4.60, 6.10)},
        {"when": "Sun 19:15", "home": "Lommel SK", "away": "Standard Liège", "odds": (3.20, 3.60, 2.12)},
    ],
}

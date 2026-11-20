"""Weekend fixtures and the bookmaker 1X2 odds (home, draw, away) supplied by the user.

Team names follow model.norm(): no trailing "FC"/"AFC".
"""

# Share of the final probability taken from the de-margined bookmaker odds.
# The odds reflect current form, injuries and the table; the model's data is
# stale (PL/CH/LaLiga end 2026-09-20; LaLiga 2 ends 2025-11-03, nothing from 2026-27;
# Serie A ends 2026-09-20, Serie B ends 2026-03-17; League One/Two end 2025-12-29), so lean on the market.
MARKET_WEIGHT = {"PL": 0.7, "CH": 0.7, "L1": 0.85, "LL": 0.7, "LL2": 0.9, "SA": 0.7}

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
}

"""Weekend fixtures and the bookmaker 1X2 odds (home, draw, away) supplied by the user.

Team names follow model.norm(): no trailing "FC"/"AFC".
"""

# The model's data ends on 2026-09-20, but the odds reflect current form,
# injuries and the table, so we lean on the market.
MARKET_WEIGHT = 0.7

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
}

"""Weekend fixtures and the bookmaker 1X2 odds (home, draw, away) supplied by the user."""

# The model's data ends on 2026-09-20, but the odds reflect current form,
# injuries and the table, so we lean on the market.
MARKET_WEIGHT = 0.7

FIXTURES = [
    {"when": "Sat 13:30", "home": "Manchester City FC", "away": "Fulham FC", "odds": (1.42, 5.20, 7.00)},
    {"when": "Sat 16:00", "home": "Tottenham Hotspur FC", "away": "Ipswich Town FC", "odds": (1.55, 4.50, 5.60)},
    {"when": "Sat 16:00", "home": "Chelsea FC", "away": "Leeds United FC", "odds": (1.92, 3.70, 4.00)},
    {"when": "Sat 16:00", "home": "Aston Villa FC", "away": "Sunderland AFC", "odds": (1.78, 3.85, 4.50)},
    {"when": "Sat 16:00", "home": "Coventry City FC", "away": "Crystal Palace FC", "odds": (2.53, 3.55, 2.74)},
    {"when": "Sat 16:00", "home": "AFC Bournemouth", "away": "Nottingham Forest FC", "odds": (1.98, 3.60, 3.85)},
    {"when": "Sat 18:30", "home": "Newcastle United FC", "away": "Arsenal FC", "odds": (5.60, 4.30, 1.58)},
    {"when": "Sun 15:00", "home": "Hull City AFC", "away": "Brighton & Hove Albion FC", "odds": (6.10, 4.50, 1.52)},
    {"when": "Sun 17:30", "home": "Liverpool FC", "away": "Manchester United FC", "odds": (1.78, 4.20, 4.10)},
]

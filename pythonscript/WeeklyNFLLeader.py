import requests
import csv
import sys
import os
from collections import defaultdict

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
SEASON = 2026
ALL_WEEKS = range(1, 19)

SCOREBOARD_URL = (
    "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/"
    "seasons/{season}/types/2/weeks/{week}/events"
)

BOXSCORE_URL = "https://cdn.espn.com/core/nfl/boxscore?xhr=1&gameId={game_id}"

TEAM_MASCOTS = {
    "SF": "49ers",
    "LAR": "Rams",
    "SEA": "Seahawks",
    "NE": "Patriots",
    "DAL": "Cowboys",
    "NYG": "Giants",
    "NYJ": "Jets",
    "PHI": "Eagles",
    "WAS": "Commanders",
    "WSH": "Commanders",
    "CHI": "Bears",
    "GB": "Packers",
    "DET": "Lions",
    "MIN": "Vikings",
    "TB": "Buccaneers",
    "ATL": "Falcons",
    "CAR": "Panthers",
    "NO": "Saints",
    "HOU": "Texans",
    "TEN": "Titans",
    "IND": "Colts",
    "JAX": "Jaguars",
    "KC": "Chiefs",
    "LV": "Raiders",
    "DEN": "Broncos",
    "LAC": "Chargers",
    "ARI": "Cardinals",
    "MIA": "Dolphins",
    "BUF": "Bills",
    "PIT": "Steelers",
    "CLE": "Browns",
    "CIN": "Bengals",
    "BAL": "Ravens"
}

STATNAMES = ["Rushing", "Receiving", "Passing", "Sacks", "Interceptions", "Tackles"]
STATCODES = ["rush", "rec", "pass", "sacks", "interceptions", "tackles"]
STATSRANGE = range(0, len(STATCODES))

# ------------------------------------------------------------
# COMMAND-LINE WEEK SELECTION
# ------------------------------------------------------------
def parse_week_args():
    if len(sys.argv) == 1:
        print("Usage:")
        print("  python WeeklyNFLLeader.py 7")
        print("  python WeeklyNFLLeader.py 7 12")
        sys.exit(1)

    if len(sys.argv) == 2:
        wk = int(sys.argv[1])
        return range(wk, wk + 1)

    if len(sys.argv) == 3:
        wk1 = int(sys.argv[1])
        wk2 = int(sys.argv[2])
        return range(wk1, wk2 + 1)

    print("Too many arguments.")
    sys.exit(1)

WEEKS_TO_PROCESS = parse_week_args()

# ------------------------------------------------------------
# HTTP
# ------------------------------------------------------------
def get_json(url):
    try:
        return requests.get(url).json()
    except Exception:
        return {}

# ------------------------------------------------------------
# BOXCORE ACCESS
# ------------------------------------------------------------
def get_gamepackage_boxscore(data):
    return data.get("gamepackageJSON", {}).get("boxscore", {})

# ------------------------------------------------------------
# STAT HELPERS
# ------------------------------------------------------------
def get_value_by_label(labels, stats, wanted_labels):
    for i, lab in enumerate(labels):
        lab_l = str(lab).lower()
        if any(w in lab_l for w in wanted_labels) and i < len(stats):
            raw = stats[i]
            try:
                return float(raw)
            except Exception:
                try:
                    return float(str(raw).split("-")[0])
                except Exception:
                    return 0.0
    return 0.0

def extract_team_player_stats(boxscore):
    team_offense = defaultdict(lambda: {
        "pass": {"value": 0.0, "player": None},
        "rush": {"value": 0.0, "player": None},
        "rec":  {"value": 0.0, "player": None},
    })

    team_defense = defaultdict(lambda: {
        "sacks": {"value": 0.0, "player": None},
        "interceptions": {"value": 0.0, "player": None},
        "tackles": {"value": 0.0, "player": None},
    })

    players_groups = boxscore.get("players", [])

    for group in players_groups:
        team = group.get("team", {})
        team_abbr = team.get("abbreviation")
        if not team_abbr:
            continue

        for cat in group.get("statistics", []):
            cname = str(cat.get("name", "")).lower()
            labels = cat.get("labels", [])
            athletes = cat.get("athletes", [])

            for a in athletes:
                athlete_info = a.get("athlete", {})
                pname = athlete_info.get("displayName")
                stats = a.get("stats", [])

                if "passing" in cname:
                    yards = get_value_by_label(labels, stats, ["yds"])
                    if yards > team_offense[team_abbr]["pass"]["value"]:
                        team_offense[team_abbr]["pass"] = {"value": yards, "player": pname}

                if "rushing" in cname:
                    yards = get_value_by_label(labels, stats, ["yds"])
                    if yards > team_offense[team_abbr]["rush"]["value"]:
                        team_offense[team_abbr]["rush"] = {"value": yards, "player": pname}

                if "receiving" in cname:
                    yards = get_value_by_label(labels, stats, ["yds"])
                    if yards > team_offense[team_abbr]["rec"]["value"]:
                        team_offense[team_abbr]["rec"] = {"value": yards, "player": pname}

                if "defensive" in cname:
                    sacks = get_value_by_label(labels, stats, ["sacks"])
                    if sacks > team_defense[team_abbr]["sacks"]["value"]:
                        team_defense[team_abbr]["sacks"] = {"value": sacks, "player": pname}

                    ints = get_value_by_label(labels, stats, ["int", "ints"])
                    if ints > team_defense[team_abbr]["interceptions"]["value"]:
                        team_defense[team_abbr]["interceptions"] = {"value": ints, "player": pname}

                    tkl = get_value_by_label(labels, stats, ["tot", "tkl"])
                    if tkl > team_defense[team_abbr]["tackles"]["value"]:
                        team_defense[team_abbr]["tackles"] = {"value": tkl, "player": pname}

                if "interceptions" in cname:
                    ints = get_value_by_label(labels, stats, ["int", "ints"])
                    if ints > team_defense[team_abbr]["interceptions"]["value"]:
                        team_defense[team_abbr]["interceptions"] = {"value": ints, "player": pname}

    return team_offense, team_defense

# ------------------------------------------------------------
# WEEK LEADERS
# ------------------------------------------------------------
def find_week_leaders_team_player(team_offense, team_defense):
    leaders = {}

    def collect_leaders(source_dict, key):
        max_val = 0.0
        for team, stats in source_dict.items():
            val = stats[key]["value"]
            if val > max_val:
                max_val = val

        if max_val == 0.0:
            return {"value": 0.0, "teams": [], "players": []}

        teams = []
        players = []
        for team, stats in source_dict.items():
            if stats[key]["value"] == max_val:
                mascot = TEAM_MASCOTS[team]
                teams.append(mascot)
                players.append(stats[key]["player"] or "")

        return {"value": max_val, "teams": teams, "players": players}

    leaders["pass"] = collect_leaders(team_offense, "pass")
    leaders["rush"] = collect_leaders(team_offense, "rush")
    leaders["rec"]  = collect_leaders(team_offense, "rec")
    leaders["sacks"] = collect_leaders(team_defense, "sacks")
    leaders["interceptions"] = collect_leaders(team_defense, "interceptions")
    leaders["tackles"] = collect_leaders(team_defense, "tackles")

    return leaders

# ------------------------------------------------------------
# LOAD EXISTING TeamScoresByWeek.csv
# ------------------------------------------------------------
existing_scores = defaultdict(dict)

if os.path.exists("TeamScoresByWeek.csv"):
    with open("TeamScoresByWeek.csv", newline="") as f:
        r = csv.reader(f)
        header = next(r, None)
        if header:
            week_cols = header[1:]
            for row in r:
                if not row:
                    continue
                team = row[0]
                for i, wkcol in enumerate(week_cols):
                    wk = int(wkcol.replace("Week", ""))
                    if i + 1 < len(row):
                        existing_scores[team][wk] = row[i + 1]
                    else:
                        existing_scores[team][wk] = ""

# ------------------------------------------------------------
# LOAD EXISTING ConcatLeader.csv and ConcatLeaderPlayers.csv
# ------------------------------------------------------------
combined_leaders = defaultdict(lambda: {
    code: {"value": 0.0, "teams": [], "players": []} for code in STATCODES
})

def load_existing_concat(team_filename, player_filename):
    if not os.path.exists(team_filename) or not os.path.exists(player_filename):
        return

    # Load teams
    with open(team_filename, newline="") as f:
        r = csv.reader(f)
        rows = list(r)

    # Skip first two header rows
    idx = 2
    current_stat_index = None

    while idx < len(rows):
        row = rows[idx]
        if not row or len(row) < 2:
            idx += 1
            continue
            
        #print(f"Row[{idx}] {row}")

        # Stat header row: ["", STATNAME]
        if row[0] == "" and row[1] in STATNAMES:
            current_stat_index = STATNAMES.index(row[1])
            idx += 1
            continue

        # Week row
        if row[0].isdigit() and current_stat_index is not None:
            week = int(row[0])
            val_str = row[1] if len(row) > 1 else ""
            try:
                value = float(val_str) if val_str != "" else 0.0
            except Exception:
                value = 0.0
            teams = row[2:] if len(row) > 2 else []
            statcode = STATCODES[current_stat_index]
            combined_leaders[week][statcode]["value"] = value
            combined_leaders[week][statcode]["teams"] = teams
        idx += 1

    # Load players
    with open(player_filename, newline="") as f:
        r = csv.reader(f)
        rows = list(r)

    idx = 2
    current_stat_index = None

    while idx < len(rows):
        row = rows[idx]
        if not row or len(row) < 2:
            idx += 1
            continue

        if row[0] == "" and row[1] in STATNAMES:
            current_stat_index = STATNAMES.index(row[1])
            idx += 1
            continue

        if row[0].isdigit() and current_stat_index is not None:
            week = int(row[0])
            val_str = row[1] if len(row) > 1 else ""
            try:
                value = float(val_str) if val_str != "" else 0.0
            except Exception:
                value = 0.0
            players = row[2:] if len(row) > 2 else []
            statcode = STATCODES[current_stat_index]
            combined_leaders[week][statcode]["value"] = value
            combined_leaders[week][statcode]["players"] = players
        idx += 1

load_existing_concat("ConcatLeader.csv", "ConcatLeaderPlayers.csv")

# ------------------------------------------------------------
# MAIN LOOP
# ------------------------------------------------------------
weekly_leaders_new = {}
week_scores = defaultdict(lambda: defaultdict(lambda: ""))

for week in WEEKS_TO_PROCESS:
    print(f"Processing Week {week}...")

    events_url = SCOREBOARD_URL.format(season=SEASON, week=week)
    events_data = get_json(events_url)
    events = events_data.get("items", [])

    week_team_offense = defaultdict(lambda: {
        "pass": {"value": 0.0, "player": None},
        "rush": {"value": 0.0, "player": None},
        "rec":  {"value": 0.0, "player": None},
    })
    week_team_defense = defaultdict(lambda: {
        "sacks": {"value": 0.0, "player": None},
        "interceptions": {"value": 0.0, "player": None},
        "tackles": {"value": 0.0, "player": None},
    })

    for event in events:
        event_ref = event.get("$ref")
        if not event_ref:
            continue

        event_data = get_json(event_ref)
        game_id = event_data.get("id")
        if not game_id:
            continue

        box_url = BOXSCORE_URL.format(game_id=game_id)
        box_data = get_json(box_url)
        boxscore = get_gamepackage_boxscore(box_data)
        gp = box_data.get("gamepackageJSON", {})

        if not boxscore:
            continue

        team_offense, team_defense = extract_team_player_stats(boxscore)

        for team, stats in team_offense.items():
            for key in ["pass", "rush", "rec"]:
                if stats[key]["value"] > week_team_offense[team][key]["value"]:
                    week_team_offense[team][key] = stats[key]

        for team, stats in team_defense.items():
            for key in ["sacks", "interceptions", "tackles"]:
                if stats[key]["value"] > week_team_defense[team][key]["value"]:
                    week_team_defense[team][key] = stats[key]

        competitors = gp.get("header", {}).get("competitions", [{}])[0].get("competitors", [])
        for comp in competitors:
            team_abbr = comp["team"]["abbreviation"]
            score = comp.get("score", "")
            week_scores[team_abbr][week] = score

    leaders = find_week_leaders_team_player(week_team_offense, week_team_defense)
    weekly_leaders_new[week] = leaders

# ------------------------------------------------------------
# MERGE SCORES INTO EXISTING
# ------------------------------------------------------------
for abbr in week_scores.keys():
    mascot = TEAM_MASCOTS.get(abbr, abbr)
    for wk in WEEKS_TO_PROCESS:
        existing_scores[mascot][wk] = week_scores[abbr].get(wk, "")

# ------------------------------------------------------------
# WRITE TeamScoresByWeek.csv
# ------------------------------------------------------------
with open("TeamScoresByWeek.csv", "w", newline="") as f:
    w = csv.writer(f)
    header = ["Team"] + [f"Week{wk}" for wk in ALL_WEEKS]
    w.writerow(header)

    for mascot in sorted(existing_scores.keys()):
        row = [mascot]
        for wk in ALL_WEEKS:
            row.append(existing_scores[mascot].get(wk, ""))
        w.writerow(row)

# ------------------------------------------------------------
# MERGE NEW WEEKLY LEADERS INTO COMBINED LEADERS
# ------------------------------------------------------------
for wk, leaders in weekly_leaders_new.items():
    for code in STATCODES:
        combined_leaders[wk][code]["value"] = leaders[code]["value"]
        combined_leaders[wk][code]["teams"] = leaders[code]["teams"]
        combined_leaders[wk][code]["players"] = leaders[code]["players"]

# ------------------------------------------------------------
# WRITE CONCAT CSVs (Teams + Players) IN EXISTING FORMAT
# ------------------------------------------------------------
def write_concat_file(filename, title, category_key):
    with open(filename, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["", title])
        w.writerow(["Week", "Top Score", "Leader", "These Columns are for additional entries in a tie"])

        for i in STATSRANGE:
            statcode = STATCODES[i]
            statname = STATNAMES[i]
            w.writerow([""])
            w.writerow(["", statname])
            for wk in ALL_WEEKS:
                entry = combined_leaders.get(wk, {}).get(statcode, None)
                if entry and (entry["value"] != 0.0 or entry[category_key]):
                    w.writerow([wk, entry["value"]] + entry[category_key])
                else:
                    w.writerow([wk])

write_concat_file("ConcatLeader.csv", "Team Stat Leaders", "teams")
write_concat_file("ConcatLeaderPlayers.csv", "Athlete Stat Leaders", "players")

print("Done. Incremental update complete.")

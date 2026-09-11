import requests
import csv
from collections import defaultdict

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
SEASON = 2026
WEEKS = range(1, 19)

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
    """
    labels: e.g. ["C/ATT","YDS","AVG","TD","INT","SACKS","RTG"]
    stats:  e.g. ["25/34","205","6.0","3","1","0-0","105.6"]
    wanted_labels: list of lowercase tokens to match, e.g. ["yds"]
    """
    for i, lab in enumerate(labels):
        lab_l = str(lab).lower()
        if lab_l in wanted_labels and i < len(stats):
            raw = stats[i]
            # handle "0-0" etc. by ignoring non-numeric
            try:
                return float(raw)
            except Exception:
                try:
                    return float(str(raw).split("-")[0])
                except Exception:
                    return 0.0
    return 0.0


def extract_team_player_stats(boxscore):
    """
    From boxscore['players'], build per-team highest:
      - pass yards
      - rush yards
      - rec yards
      - sacks
      - interceptions
      - tackles
    """
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

                # Passing
                if "passing" in cname:
                    yards = get_value_by_label(labels, stats, ["yds"])
                    if yards > team_offense[team_abbr]["pass"]["value"]:
                        team_offense[team_abbr]["pass"] = {
                            "value": yards,
                            "player": pname,
                        }

                # Rushing
                if "rushing" in cname:
                    yards = get_value_by_label(labels, stats, ["yds"])
                    if yards > team_offense[team_abbr]["rush"]["value"]:
                        team_offense[team_abbr]["rush"] = {
                            "value": yards,
                            "player": pname,
                        }

                # Receiving
                if "receiving" in cname:
                    yards = get_value_by_label(labels, stats, ["yds"])
                    if yards > team_offense[team_abbr]["rec"]["value"]:
                        team_offense[team_abbr]["rec"] = {
                            "value": yards,
                            "player": pname,
                        }

                # Defensive
                if "defensive" in cname:
                    sacks = get_value_by_label(labels, stats, ["sacks"])
                    if sacks > team_defense[team_abbr]["sacks"]["value"]:
                        team_defense[team_abbr]["sacks"] = {
                            "value": sacks,
                            "player": pname,
                        }

                    ints = get_value_by_label(labels, stats, ["int"])
                    if ints > team_defense[team_abbr]["interceptions"]["value"]:
                        team_defense[team_abbr]["interceptions"] = {
                            "value": ints,
                            "player": pname,
                        }

                    # tackles often labeled "TOT" or "TKL"
                    tkl = get_value_by_label(labels, stats, ["tot", "tkl"])
                    if tkl > team_defense[team_abbr]["tackles"]["value"]:
                        team_defense[team_abbr]["tackles"] = {
                            "value": tkl,
                            "player": pname,
                        }

    return team_offense, team_defense


# ------------------------------------------------------------
# WEEK LEADERS (TEAM + PLAYER, TIE-AWARE)
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

    leaders["sacks"]         = collect_leaders(team_defense, "sacks")
    leaders["interceptions"] = collect_leaders(team_defense, "interceptions")
    leaders["tackles"]       = collect_leaders(team_defense, "tackles")

    return leaders


# ------------------------------------------------------------
# CSV HELPERS
# ------------------------------------------------------------
def open_csv_pair(stat_name, write_header=True):
    team_file = open(f"{stat_name}Leader.csv", "w", newline="")
    player_file = open(f"{stat_name}LeaderPlayers.csv", "w", newline="")

    team_writer = csv.writer(team_file)
    player_writer = csv.writer(player_file)

    if write_header:
        team_writer.writerow(["Week", "Value", "Teams"])
        player_writer.writerow(["Week", "Value", "Players"])

    return (team_file, team_writer), (player_file, player_writer)


(rush_team_f, rush_team_w), (rush_player_f, rush_player_w) = open_csv_pair("Rush")
(rec_team_f,  rec_team_w),  (rec_player_f,  rec_player_w)  = open_csv_pair("Receive")
(pass_team_f, pass_team_w), (pass_player_f, pass_player_w) = open_csv_pair("Pass")
(sack_team_f, sack_team_w), (sack_player_f, sack_player_w) = open_csv_pair("Sack")
(int_team_f,  int_team_w),  (int_player_f,  int_player_w)  = open_csv_pair("INT")
(tkl_team_f,  tkl_team_w),  (tkl_player_f,  tkl_player_w)  = open_csv_pair("Tackle")

(concat_team_f, concat_team_w), (concat_player_f, concat_player_w) = open_csv_pair("Concat", write_header=False)

numWeeks = 0
# ------------------------------------------------------------
# MAIN LOOP
# ------------------------------------------------------------
for week in WEEKS:
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
            print("  Skipping event: no game_id")
            continue

        box_url = BOXSCORE_URL.format(game_id=game_id)
        box_data = get_json(box_url)
        boxscore = get_gamepackage_boxscore(box_data)

        if not boxscore:
            print(f"  Skipping game {game_id}: no boxscore")
            continue

        team_offense, team_defense = extract_team_player_stats(boxscore)

        # Merge into week-level highest per team
        for team, stats in team_offense.items():
            for key in ["pass", "rush", "rec"]:
                if stats[key]["value"] > week_team_offense[team][key]["value"]:
                    week_team_offense[team][key] = stats[key]

        for team, stats in team_defense.items():
            for key in ["sacks", "interceptions", "tackles"]:
                if stats[key]["value"] > week_team_defense[team][key]["value"]:
                    week_team_defense[team][key] = stats[key]

    if not week_team_offense and not week_team_defense:
        print(f"  Week {week}: no stats found. Stopping")
        break;
    numWeeks = numWeeks + 1
    
    leaders = find_week_leaders_team_player(week_team_offense, week_team_defense)

    # Team CSVs
    rush_team_w.writerow([week, leaders["rush"]["value"]] + leaders["rush"]["teams"])
    rec_team_w.writerow([week, leaders["rec"]["value"]] + leaders["rec"]["teams"])
    pass_team_w.writerow([week, leaders["pass"]["value"]] + leaders["pass"]["teams"])
    sack_team_w.writerow([week, leaders["sacks"]["value"]] + leaders["sacks"]["teams"])
    int_team_w.writerow([week, leaders["interceptions"]["value"]] + leaders["interceptions"]["teams"])
    tkl_team_w.writerow([week, leaders["tackles"]["value"]] + leaders["tackles"]["teams"])


    # Player CSVs
    rush_player_w.writerow([week, leaders["rush"]["value"]] + leaders["rush"]["players"])
    rec_player_w.writerow([week, leaders["rec"]["value"]] + leaders["rec"]["players"])
    pass_player_w.writerow([week, leaders["pass"]["value"]] + leaders["pass"]["players"])
    sack_player_w.writerow([week, leaders["sacks"]["value"]] + leaders["sacks"]["players"])
    int_player_w.writerow([week, leaders["interceptions"]["value"]] + leaders["interceptions"]["players"])
    tkl_player_w.writerow([week, leaders["tackles"]["value"]] + leaders["tackles"]["players"])

print("Done. CSV files written. Writing concatenated CSVS...")

def write_concat_csv(csv_writer, title, category):
    csv_writer.writerow(["",title])
    csv_writer.writerow(["Week", "Top Score", "Leader", "These Columns are for additional entries in a tie"])
    for i in STATSRANGE:
        csv_writer.writerow([""])
        csv_writer.writerow(["",STATNAMES[i]])
        for week in WEEKS:
            if (week <= numWeeks):
                csv_writer.writerow([week, leaders[STATCODES[i]]["value"]] + leaders[STATCODES[i]][category])
            else:
                csv_writer.writerow([week])
           


#
# Write the Concat file for Teams
#
write_concat_csv(concat_team_w, "Team Stat Leaders", "teams")

#
# Write the Concat file for Players
#
write_concat_csv(concat_player_w, "Athlete Stat Leaders", "players")

for f in [
    rush_team_f, rush_player_f,
    rec_team_f,  rec_player_f,
    pass_team_f, pass_player_f,
    sack_team_f, sack_player_f,
    int_team_f,  int_player_f,
    tkl_team_f,  tkl_player_f,
    concat_team_f, concat_player_f,
]:
    f.close()

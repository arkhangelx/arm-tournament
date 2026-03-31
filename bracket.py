import math
import random
import pandas as pd


def next_power_of_two(n: int) -> int:
    return 1 if n == 0 else 2 ** math.ceil(math.log2(n))


def add_bye_players(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    target = next_power_of_two(n)
    byes_needed = target - n

    df = df.copy()
    if "is_bye" not in df.columns:
        df["is_bye"] = False
    else:
        df["is_bye"] = df["is_bye"].fillna(False)

    bye_rows = []
    for i in range(byes_needed):
        bye_rows.append({
            "id": f"BYE_{i+1}",
            "full_name": "BYE",
            "weight": "",
            "faculty": "",
            "weight_class": "",
            "losses": 0,
            "status": "bye",
            "is_bye": True
        })

    if bye_rows:
        df = pd.concat([df, pd.DataFrame(bye_rows)], ignore_index=True)

    return df


def add_single_bye_if_needed(players: list[dict]) -> list[dict]:
    players = players.copy()
    if len(players) % 2 == 1:
        players.append({
            "id": f"BYE_DYNAMIC_{len(players)+1}",
            "full_name": "BYE",
            "weight": "",
            "faculty": "",
            "weight_class": "",
            "losses": 0,
            "status": "bye",
            "is_bye": True
        })
    return players


def players_to_pairs(players: list[dict], shuffle: bool = True) -> list[tuple[dict, dict]]:
    players = players.copy()
    if shuffle:
        random.shuffle(players)

    pairs = []
    for i in range(0, len(players), 2):
        pairs.append((players[i], players[i + 1]))
    return pairs


def dataframe_to_players(df: pd.DataFrame) -> list[dict]:
    return df.to_dict("records")


def create_round_from_players(players: list[dict], round_number: int, bracket_type: str) -> list[dict]:
    players = add_single_bye_if_needed(players)
    pairs = players_to_pairs(players, shuffle=True)
    prefix = "U" if bracket_type == "upper" else "L"

    matches = []

    for i, (p1, p2) in enumerate(pairs):
        match = {
            "match_id": f"{prefix}{round_number}_{i+1}",
            "round": round_number,
            "bracket": bracket_type,
            "player1": p1,
            "player2": p2,
            "winner": None,
            "loser": None,
            "status": "pending"
        }

        if p1["full_name"] == "BYE":
            match["winner"] = p2
            match["loser"] = p1
            match["status"] = "done"
        elif p2["full_name"] == "BYE":
            match["winner"] = p1
            match["loser"] = p2
            match["status"] = "done"

        matches.append(match)

    return matches


def create_first_upper_round(df: pd.DataFrame) -> list[dict]:
    df = add_bye_players(df)
    players = dataframe_to_players(df)
    return create_round_from_players(players, round_number=1, bracket_type="upper")


def set_match_winner(match: dict, winner_side: int) -> dict:
    updated = match.copy()

    p1 = updated["player1"]
    p2 = updated["player2"]

    if winner_side == 1:
        updated["winner"] = p1
        updated["loser"] = p2
    elif winner_side == 2:
        updated["winner"] = p2
        updated["loser"] = p1
    else:
        raise ValueError("winner_side должен быть 1 или 2")

    updated["status"] = "done"
    return updated


def reset_match_winner(match: dict) -> dict:
    updated = match.copy()
    updated["winner"] = None
    updated["loser"] = None
    updated["status"] = "pending"
    return updated


def round_is_complete(matches: list[dict]) -> bool:
    return all(match["status"] == "done" for match in matches)


def collect_round_results(matches: list[dict]) -> tuple[list[dict], list[dict]]:
    winners = []
    losers = []

    for match in matches:
        if match["status"] == "done":
            if match["winner"] and match["winner"]["full_name"] != "BYE":
                winners.append(match["winner"])
            if match["loser"] and match["loser"]["full_name"] != "BYE":
                losers.append(match["loser"])

    return winners, losers


def can_create_next_upper_round(upper_rounds: list[list[dict]]) -> bool:
    if not upper_rounds:
        return False

    last_round = upper_rounds[-1]
    if not round_is_complete(last_round):
        return False

    winners, _ = collect_round_results(last_round)
    return len(winners) >= 2


def create_next_upper_round(upper_rounds: list[list[dict]]) -> list[dict]:
    if not can_create_next_upper_round(upper_rounds):
        return []

    last_round = upper_rounds[-1]
    winners, _ = collect_round_results(last_round)

    next_round_number = len(upper_rounds) + 1
    return create_round_from_players(winners, round_number=next_round_number, bracket_type="upper")


def get_upper_bracket_finalist(upper_rounds: list[list[dict]]) -> dict | None:
    if not upper_rounds:
        return None

    last_round = upper_rounds[-1]
    if not round_is_complete(last_round):
        return None

    winners, _ = collect_round_results(last_round)
    if len(winners) == 1:
        return winners[0]

    return None


# --------------------------
# Нижняя сетка
# --------------------------

def can_create_next_lower_round(lower_waiting: list[dict], lower_rounds: list[list[dict]]) -> bool:
    if lower_rounds:
        last_lower_round = lower_rounds[-1]
        if not round_is_complete(last_lower_round):
            return False

    return len(lower_waiting) >= 2


def create_next_lower_round(lower_waiting: list[dict], lower_rounds: list[list[dict]]) -> tuple[list[dict], list[dict]]:
    if not can_create_next_lower_round(lower_waiting, lower_rounds):
        return [], lower_waiting

    players = lower_waiting.copy()
    players = add_single_bye_if_needed(players)

    next_round_number = len(lower_rounds) + 1
    round_matches = create_round_from_players(players, next_round_number, "lower")

    return round_matches, []


def get_lower_round_survivors(lower_rounds: list[list[dict]]) -> list[dict]:
    if not lower_rounds:
        return []

    last_round = lower_rounds[-1]
    if not round_is_complete(last_round):
        return []

    winners, _ = collect_round_results(last_round)
    return winners


def get_eliminated_from_lower_round(lower_rounds: list[list[dict]]) -> list[dict]:
    if not lower_rounds:
        return []

    last_round = lower_rounds[-1]
    if not round_is_complete(last_round):
        return []

    _, losers = collect_round_results(last_round)
    return losers


def get_lower_bracket_finalist(upper_finalist: dict | None, lower_waiting: list[dict], lower_rounds: list[list[dict]]) -> dict | None:
    if upper_finalist is None:
        return None

    if lower_waiting:
        return None

    if not lower_rounds:
        return None

    last_round = lower_rounds[-1]
    if not round_is_complete(last_round):
        return None

    winners, _ = collect_round_results(last_round)
    if len(winners) == 1:
        return winners[0]

    return None


# --------------------------
# Суперфинал
# --------------------------

def create_superfinal(upper_finalist: dict, lower_finalist: dict, mode: str = "handicap") -> dict:
    """
    mode:
    - handicap: верхней сетке нужно 2 победы, нижней 3
    - simple: обоим нужна 1 победа
    """
    if mode == "handicap":
        upper_target = 2
        lower_target = 3
    else:
        upper_target = 1
        lower_target = 1

    return {
        "player_upper": upper_finalist,
        "player_lower": lower_finalist,
        "upper_wins": 0,
        "lower_wins": 0,
        "upper_target": upper_target,
        "lower_target": lower_target,
        "status": "in_progress",
        "winner": None,
        "runner_up": None,
        "mode": mode,
        "games": []
    }


def register_superfinal_win(superfinal: dict, winner_side: str) -> dict:
    """
    winner_side:
    - 'upper'
    - 'lower'
    """
    sf = superfinal.copy()
    sf["games"] = sf["games"].copy()

    if sf["status"] == "done":
        return sf

    if winner_side == "upper":
        sf["upper_wins"] += 1
        sf["games"].append("upper")
    elif winner_side == "lower":
        sf["lower_wins"] += 1
        sf["games"].append("lower")
    else:
        raise ValueError("winner_side должен быть 'upper' или 'lower'")

    if sf["upper_wins"] >= sf["upper_target"]:
        sf["status"] = "done"
        sf["winner"] = sf["player_upper"]
        sf["runner_up"] = sf["player_lower"]

    if sf["lower_wins"] >= sf["lower_target"]:
        sf["status"] = "done"
        sf["winner"] = sf["player_lower"]
        sf["runner_up"] = sf["player_upper"]

    return sf

def undo_last_superfinal_win(superfinal: dict) -> dict:
    sf = superfinal.copy()
    sf["games"] = sf.get("games", []).copy()

    if not sf["games"]:
        return sf

    last_game = sf["games"].pop()
    if last_game == "upper" and sf.get("upper_wins", 0) > 0:
        sf["upper_wins"] -= 1
    elif last_game == "lower" and sf.get("lower_wins", 0) > 0:
        sf["lower_wins"] -= 1

    sf["status"] = "in_progress"
    sf["winner"] = None
    sf["runner_up"] = None
    return sf

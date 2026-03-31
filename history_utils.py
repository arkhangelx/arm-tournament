import pandas as pd


def build_match_history(upper_rounds, lower_rounds, superfinal):
    rows = []

    # Верхняя сетка
    for round_matches in upper_rounds or []:
        for match in round_matches:
            rows.append({
                "stage": "upper",
                "round": match.get("round", ""),
                "match_id": match.get("match_id", ""),
                "player1": match.get("player1", {}).get("full_name", ""),
                "player2": match.get("player2", {}).get("full_name", ""),
                "winner": match.get("winner", {}).get("full_name", "") if match.get("winner") else "",
                "loser": match.get("loser", {}).get("full_name", "") if match.get("loser") else "",
                "status": match.get("status", ""),
            })

    # Нижняя сетка
    for round_matches in lower_rounds or []:
        for match in round_matches:
            rows.append({
                "stage": "lower",
                "round": match.get("round", ""),
                "match_id": match.get("match_id", ""),
                "player1": match.get("player1", {}).get("full_name", ""),
                "player2": match.get("player2", {}).get("full_name", ""),
                "winner": match.get("winner", {}).get("full_name", "") if match.get("winner") else "",
                "loser": match.get("loser", {}).get("full_name", "") if match.get("loser") else "",
                "status": match.get("status", ""),
            })

    # Суперфинал
    if superfinal is not None:
        upper_name = superfinal.get("player_upper", {}).get("full_name", "")
        lower_name = superfinal.get("player_lower", {}).get("full_name", "")

        for i, game_winner in enumerate(superfinal.get("games", []), start=1):
            winner_name = upper_name if game_winner == "upper" else lower_name
            loser_name = lower_name if game_winner == "upper" else upper_name

            rows.append({
                "stage": "superfinal",
                "round": i,
                "match_id": f"SF_{i}",
                "player1": upper_name,
                "player2": lower_name,
                "winner": winner_name,
                "loser": loser_name,
                "status": "done",
            })

    df = pd.DataFrame(rows)

    if not df.empty:
        stage_order = {"upper": 1, "lower": 2, "superfinal": 3}
        df["stage_order"] = df["stage"].map(stage_order)
        df = df.sort_values(by=["stage_order", "round", "match_id"]).reset_index(drop=True)
        df = df.drop(columns=["stage_order"])

    return df


def build_elimination_history(eliminated_players):
    rows = []

    for i, player in enumerate(eliminated_players or [], start=1):
        rows.append({
            "out_order": i,
            "full_name": player.get("full_name", ""),
            "weight": player.get("weight", ""),
            "faculty": player.get("faculty", ""),
        })

    return pd.DataFrame(rows)
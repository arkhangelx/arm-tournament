import streamlit as st
import pandas as pd

from sheets_sync import sync_all, open_spreadsheet, clear_participant_data
from bracket import (
    create_first_upper_round,
    set_match_winner,
    reset_match_winner,
    round_is_complete,
    collect_round_results,
    create_next_upper_round,
    can_create_next_upper_round,
    get_upper_bracket_finalist,
    can_create_next_lower_round,
    create_next_lower_round,
    get_lower_round_survivors,
    get_eliminated_from_lower_round,
    get_lower_bracket_finalist,
    create_superfinal,
    register_superfinal_win,
    undo_last_superfinal_win,
)
from history_utils import build_match_history, build_elimination_history
from storage import init_db, upsert_tournament, list_tournaments, load_tournament, clear_all_tournaments

st.set_page_config(page_title="Arm Tournament Sync", layout="wide")
init_db()

st.title("Армрестлинг — турнирная система")

st.info(
    "Категории:\n"
    "- Мужчины: до 60, до 70, до 80, до 90, выше 90\n"
    "- Женщины: до 50, до 60, выше 60"
)


# -----------------------------
# Вспомогательные функции
# -----------------------------
def collect_persisted_state():
    keys_to_save = [
        "current_tournament_id",
        "selected_category_for_matches",
        "upper_rounds",
        "lower_rounds",
        "lower_waiting",
        "eliminated_players",
        "processed_upper_rounds_for_lower",
        "last_processed_lower_round",
        "superfinal",
        "tournament_started",
    ]
    return {key: st.session_state.get(key) for key in keys_to_save}


def apply_loaded_state(state: dict):
    for key, value in state.items():
        st.session_state[key] = value


def reset_tournament_state():
    keys_to_clear = [
        "current_tournament_id",
        "selected_category_for_matches",
        "upper_rounds",
        "lower_rounds",
        "lower_waiting",
        "eliminated_players",
        "processed_upper_rounds_for_lower",
        "last_processed_lower_round",
        "superfinal",
        "tournament_started",
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]


def build_places_df():
    sf = st.session_state.get("superfinal")
    if sf is None or sf.get("status") != "done":
        return pd.DataFrame(columns=["place", "full_name", "weight", "faculty"])

    first_place = sf["winner"]
    second_place = sf["runner_up"]

    places = [
        {
            "place": 1,
            "full_name": first_place["full_name"],
            "weight": first_place.get("weight", ""),
            "faculty": first_place.get("faculty", ""),
        },
        {
            "place": 2,
            "full_name": second_place["full_name"],
            "weight": second_place.get("weight", ""),
            "faculty": second_place.get("faculty", ""),
        },
    ]

    eliminated = st.session_state.get("eliminated_players", [])
    if eliminated:
        third_place = eliminated[-1]
        places.append(
            {
                "place": 3,
                "full_name": third_place["full_name"],
                "weight": third_place.get("weight", ""),
                "faculty": third_place.get("faculty", ""),
            }
        )

    return pd.DataFrame(places)


def get_tournament_status():
    sf = st.session_state.get("superfinal")
    if sf is not None and sf.get("status") == "done":
        return "finished"
    if st.session_state.get("tournament_started"):
        return "active"
    return "draft"


def save_current_tournament():
    if not st.session_state.get("tournament_started"):
        return None

    category = st.session_state.get("selected_category_for_matches", "unknown")
    state = collect_persisted_state()
    history_df = build_match_history(
        st.session_state.get("upper_rounds", []),
        st.session_state.get("lower_rounds", []),
        st.session_state.get("superfinal"),
    )
    places_df = build_places_df()
    status = get_tournament_status()

    tournament_id = upsert_tournament(
        tournament_id=st.session_state.get("current_tournament_id"),
        category=category,
        status=status,
        state=state,
        history_df=history_df,
        placements_df=places_df,
    )

    st.session_state["current_tournament_id"] = tournament_id
    return tournament_id


def load_category_sheet(category_name: str) -> pd.DataFrame:
    spreadsheet = open_spreadsheet()
    ws = spreadsheet.worksheet(category_name)
    data = ws.get_all_records()
    return pd.DataFrame(data)


def start_new_tournament_for_category(category_name: str):
    df = load_category_sheet(category_name)
    if df.empty:
        raise ValueError("В выбранной категории нет участников")

    first_round = create_first_upper_round(df)

    st.session_state["current_tournament_id"] = None
    st.session_state["selected_category_for_matches"] = category_name
    st.session_state["upper_rounds"] = [first_round]
    st.session_state["lower_rounds"] = []
    st.session_state["lower_waiting"] = []
    st.session_state["eliminated_players"] = []
    st.session_state["processed_upper_rounds_for_lower"] = []
    st.session_state["last_processed_lower_round"] = 0
    st.session_state["superfinal"] = None
    st.session_state["tournament_started"] = True

    return save_current_tournament()


def can_undo_upper_match(round_idx: int) -> bool:
    upper_rounds = st.session_state.get("upper_rounds", [])
    lower_rounds = st.session_state.get("lower_rounds", [])
    superfinal = st.session_state.get("superfinal")
    processed = st.session_state.get("processed_upper_rounds_for_lower", [])

    if round_idx != len(upper_rounds) - 1:
        return False
    if lower_rounds:
        return False
    if superfinal is not None:
        return False
    if (round_idx + 1) in processed:
        return False
    return True


def can_undo_lower_match(round_idx: int) -> bool:
    lower_rounds = st.session_state.get("lower_rounds", [])
    superfinal = st.session_state.get("superfinal")
    last_processed_lower_round = st.session_state.get("last_processed_lower_round", 0)

    if round_idx != len(lower_rounds) - 1:
        return False
    if superfinal is not None:
        return False
    if last_processed_lower_round == len(lower_rounds):
        return False
    return True



# -----------------------------
# Sidebar: управление турнирами
# -----------------------------
with st.sidebar:
    st.header("Управление")

    if st.button("Синхронизировать таблицу"):
        try:
            result = sync_all()
            st.session_state["last_sync_result"] = result
            st.success("Синхронизация завершена")
        except Exception as e:
            st.error(f"Ошибка синхронизации: {e}")

    try:
        spreadsheet = open_spreadsheet()
        worksheets = spreadsheet.worksheets()
        category_sheets = [
            ws.title for ws in worksheets
            if ws.title.startswith("M_") or ws.title.startswith("W_")
        ]
    except Exception as e:
        category_sheets = []
        st.error(f"Ошибка чтения категорий: {e}")

    selected_category = st.selectbox(
        "Категория",
        category_sheets if category_sheets else ["—"],
        key="sidebar_selected_category"
    )

    existing_tournaments = list_tournaments(
        selected_category if selected_category != "—" else None
    )

    def format_tournament_option(t):
        return f"ID {t['id']} | {t['category']} | {t['status']} | {t['updated_at'][:16]}"

    selected_tournament = st.selectbox(
        "Сохранённые турниры категории",
        existing_tournaments,
        format_func=format_tournament_option if existing_tournaments else lambda x: "Нет турниров",
        key="sidebar_selected_tournament",
    ) if existing_tournaments else None

    if st.button("Создать новый турнир"):
        if selected_category == "—":
            st.warning("Нет доступной категории")
        else:
            try:
                tid = start_new_tournament_for_category(selected_category)
                st.success(f"Создан новый турнир. ID: {tid}")
                st.rerun()
            except Exception as e:
                st.error(f"Не удалось создать турнир: {e}")

    if st.button("Загрузить выбранный турнир"):
        if selected_tournament is None:
            st.warning("Нет турнира для загрузки")
        else:
            loaded = load_tournament(selected_tournament["id"])
            if loaded is None:
                st.error("Турнир не найден")
            else:
                apply_loaded_state(loaded["state"])
                st.session_state["current_tournament_id"] = loaded["id"]
                st.success(f"Загружен турнир ID {loaded['id']}")
                st.rerun()

    if st.button("Сохранить текущий турнир"):
        tid = save_current_tournament()
        if tid is None:
            st.warning("Нет активного турнира")
        else:
            st.success(f"Турнир сохранён. ID: {tid}")

    if st.button("Сбросить текущее состояние"):
        reset_tournament_state()
        st.success("Состояние очищено")
        st.rerun()

    if st.button("Перезапустить турнир текущей категории"):
        current_category = st.session_state.get("selected_category_for_matches") or selected_category
        if not current_category or current_category == "—":
            st.warning("Сначала выбери категорию")
        else:
            try:
                tid = start_new_tournament_for_category(current_category)
                st.success(f"Турнир перезапущен. Новый ID: {tid}")
                st.rerun()
            except Exception as e:
                st.error(f"Не удалось перезапустить турнир: {e}")

    confirm_full_reset = st.checkbox("Подтверждаю полную очистку турниров и участников", key="confirm_full_reset")
    if st.button("Очистить вообще всё"):
        if not confirm_full_reset:
            st.warning("Поставь галочку подтверждения перед полной очисткой")
        else:
            try:
                clear_all_tournaments()
                clear_participant_data(clear_raw=True)
                reset_tournament_state()
                st.success("Удалены все турниры, история и участники")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка полной очистки: {e}")

    if st.session_state.get("current_tournament_id"):
        st.caption(f"Текущий турнир ID: {st.session_state['current_tournament_id']}")


# -----------------------------
# Блок статистики синхронизации
# -----------------------------
if "last_sync_result" in st.session_state:
    st.markdown("## Синхронизация")
    result = st.session_state["last_sync_result"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Сырьевых ответов", result["raw_count"])
    c2.metric("После очистки", result["clean_count"])
    c3.metric("Валидных", result["valid_count"])
    c4.metric("С ошибками", result["invalid_count"])


# -----------------------------
# Основной интерфейс турнира
# -----------------------------
if st.session_state.get("tournament_started"):
    st.markdown("---")
    st.subheader(
        f"Турнир: {st.session_state.get('selected_category_for_matches', '')}"
    )

    upper_col, lower_col = st.columns(2)

    upper_mutated = False
    lower_mutated = False

    # -------------------------
    # Левая колонка: верхняя сетка
    # -------------------------
    with upper_col:
        st.markdown("## Верхняя сетка")

        upper_rounds = st.session_state.get("upper_rounds", [])
        updated_upper_rounds = []

        for round_idx, round_matches in enumerate(upper_rounds):
            st.subheader(f"Раунд {round_idx + 1}")
            updated_round_matches = []

            for match_idx, match in enumerate(round_matches):
                p1 = match["player1"]
                p2 = match["player2"]

                with st.container():
                    st.markdown(f"### {match['match_id']}")

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**{p1['full_name']}**")
                        st.write(f"Вес: {p1.get('weight', '')}")
                        st.write(f"Факультет: {p1.get('faculty', '')}")

                    with col2:
                        st.write(f"**{p2['full_name']}**")
                        st.write(f"Вес: {p2.get('weight', '')}")
                        st.write(f"Факультет: {p2.get('faculty', '')}")

                    if match["status"] == "done":
                        st.success(f"Победитель: {match['winner']['full_name']}")
                        if match["winner"]["full_name"] != "BYE" and can_undo_upper_match(round_idx):
                            if st.button("Отменить выбор", key=f"undo_u_{round_idx}_{match_idx}"):
                                match = reset_match_winner(match)
                                upper_mutated = True
                                st.session_state["processed_upper_rounds_for_lower"] = []
                                st.session_state["lower_waiting"] = []
                                save_current_tournament()
                                st.rerun()
                    else:
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button(f"Победил {p1['full_name']}", key=f"u_{round_idx}_{match_idx}_1"):
                                match = set_match_winner(match, 1)
                                upper_mutated = True
                        with b2:
                            if st.button(f"Победил {p2['full_name']}", key=f"u_{round_idx}_{match_idx}_2"):
                                match = set_match_winner(match, 2)
                                upper_mutated = True

                        if match["status"] == "done":
                            st.success(f"Победитель: {match['winner']['full_name']}")

                    updated_round_matches.append(match)
                    st.markdown("---")

            updated_upper_rounds.append(updated_round_matches)

        st.session_state["upper_rounds"] = updated_upper_rounds

        # передача проигравших из верхней в нижнюю
        processed = st.session_state.get("processed_upper_rounds_for_lower", [])
        lower_waiting = st.session_state.get("lower_waiting", [])

        for idx, round_matches in enumerate(updated_upper_rounds, start=1):
            if idx not in processed and round_is_complete(round_matches):
                _, losers = collect_round_results(round_matches)
                lower_waiting.extend(losers)
                processed.append(idx)
                upper_mutated = True

        st.session_state["lower_waiting"] = lower_waiting
        st.session_state["processed_upper_rounds_for_lower"] = processed

        if updated_upper_rounds:
            last_upper = updated_upper_rounds[-1]
            if round_is_complete(last_upper) and can_create_next_upper_round(updated_upper_rounds):
                if st.button("Создать следующий раунд верхней сетки"):
                    next_round = create_next_upper_round(updated_upper_rounds)
                    st.session_state["upper_rounds"].append(next_round)
                    save_current_tournament()
                    st.rerun()

        upper_finalist = get_upper_bracket_finalist(updated_upper_rounds)
        if upper_finalist:
            st.success(f"Победитель верхней сетки: {upper_finalist['full_name']}")

    # -------------------------
    # Правая колонка: нижняя сетка
    # -------------------------
    with lower_col:
        st.markdown("## Нижняя сетка")

        lower_waiting = st.session_state.get("lower_waiting", [])
        lower_rounds = st.session_state.get("lower_rounds", [])

        if lower_waiting:
            st.write("Ожидают входа в нижнюю сетку:")
            wait_df = pd.DataFrame(lower_waiting)
            st.dataframe(wait_df[["id", "full_name", "weight", "faculty"]], use_container_width=True)

        if can_create_next_lower_round(lower_waiting, lower_rounds):
            if st.button("Создать следующий раунд нижней сетки"):
                new_lower_round, updated_waiting = create_next_lower_round(lower_waiting, lower_rounds)
                st.session_state["lower_rounds"].append(new_lower_round)
                st.session_state["lower_waiting"] = updated_waiting
                save_current_tournament()
                st.rerun()

        updated_lower_rounds = []

        for round_idx, round_matches in enumerate(lower_rounds):
            st.subheader(f"Раунд {round_idx + 1}")
            updated_round_matches = []

            for match_idx, match in enumerate(round_matches):
                p1 = match["player1"]
                p2 = match["player2"]

                with st.container():
                    st.markdown(f"### {match['match_id']}")

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**{p1['full_name']}**")
                        st.write(f"Вес: {p1.get('weight', '')}")
                        st.write(f"Факультет: {p1.get('faculty', '')}")

                    with col2:
                        st.write(f"**{p2['full_name']}**")
                        st.write(f"Вес: {p2.get('weight', '')}")
                        st.write(f"Факультет: {p2.get('faculty', '')}")

                    if match["status"] == "done":
                        st.success(f"Победитель: {match['winner']['full_name']}")
                        if match["winner"]["full_name"] != "BYE" and can_undo_lower_match(round_idx):
                            if st.button("Отменить выбор", key=f"undo_l_{round_idx}_{match_idx}"):
                                match = reset_match_winner(match)
                                lower_mutated = True
                                save_current_tournament()
                                st.rerun()
                    else:
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button(f"Победил {p1['full_name']}", key=f"l_{round_idx}_{match_idx}_1"):
                                match = set_match_winner(match, 1)
                                lower_mutated = True
                        with b2:
                            if st.button(f"Победил {p2['full_name']}", key=f"l_{round_idx}_{match_idx}_2"):
                                match = set_match_winner(match, 2)
                                lower_mutated = True

                        if match["status"] == "done":
                            st.success(f"Победитель: {match['winner']['full_name']}")

                    updated_round_matches.append(match)
                    st.markdown("---")

            updated_lower_rounds.append(updated_round_matches)

        st.session_state["lower_rounds"] = updated_lower_rounds

        if updated_lower_rounds:
            last_lower = updated_lower_rounds[-1]
            if round_is_complete(last_lower):
                if st.session_state.get("last_processed_lower_round") != len(updated_lower_rounds):
                    lower_survivors = get_lower_round_survivors(updated_lower_rounds)
                    lower_eliminated = get_eliminated_from_lower_round(updated_lower_rounds)

                    st.session_state["lower_waiting"].extend(lower_survivors)
                    st.session_state["eliminated_players"].extend(lower_eliminated)
                    st.session_state["last_processed_lower_round"] = len(updated_lower_rounds)
                    lower_mutated = True

        lower_finalist = get_lower_bracket_finalist(
            get_upper_bracket_finalist(st.session_state.get("upper_rounds", [])),
            st.session_state.get("lower_waiting", []),
            st.session_state.get("lower_rounds", [])
        )
        if lower_finalist:
            st.success(f"Победитель нижней сетки: {lower_finalist['full_name']}")

    # автосохранение после изменений в матчах
    if upper_mutated or lower_mutated:
        save_current_tournament()

    # -------------------------
    # Финалисты
    # -------------------------
    st.markdown("---")
    st.markdown("## Финалисты")

    upper_finalist = get_upper_bracket_finalist(st.session_state.get("upper_rounds", []))
    lower_finalist = get_lower_bracket_finalist(
        upper_finalist,
        st.session_state.get("lower_waiting", []),
        st.session_state.get("lower_rounds", [])
    )

    if upper_finalist:
        st.write(f"**Верхняя сетка:** {upper_finalist['full_name']}")
    if lower_finalist:
        st.write(f"**Нижняя сетка:** {lower_finalist['full_name']}")

    # -------------------------
    # Суперфинал
    # -------------------------
    if upper_finalist and lower_finalist:
        st.markdown("---")
        st.markdown("## Суперфинал")

        if st.session_state.get("superfinal") is None:
            mode = st.radio(
                "Режим суперфинала",
                options=["handicap", "simple"],
                format_func=lambda x: "С гандикапом" if x == "handicap" else "Без гандикапа",
                key="superfinal_mode"
            )

            if st.button("Создать суперфинал"):
                st.session_state["superfinal"] = create_superfinal(upper_finalist, lower_finalist, mode=mode)
                save_current_tournament()
                st.rerun()

        sf = st.session_state.get("superfinal")

        if sf is not None:
            st.write(f"**Верхняя сетка:** {sf['player_upper']['full_name']}")
            st.write(f"**Нижняя сетка:** {sf['player_lower']['full_name']}")

            c1, c2 = st.columns(2)
            c1.metric("Победы верхней сетки", f"{sf['upper_wins']} / {sf['upper_target']}")
            c2.metric("Победы нижней сетки", f"{sf['lower_wins']} / {sf['lower_target']}")

            if sf["status"] != "done":
                b1, b2 = st.columns(2)
                with b1:
                    if st.button(f"Победил {sf['player_upper']['full_name']}"):
                        st.session_state["superfinal"] = register_superfinal_win(sf, "upper")
                        save_current_tournament()
                        st.rerun()
                with b2:
                    if st.button(f"Победил {sf['player_lower']['full_name']}"):
                        st.session_state["superfinal"] = register_superfinal_win(sf, "lower")
                        save_current_tournament()
                        st.rerun()

            if sf.get("games"):
                if st.button("Отменить последний результат суперфинала"):
                    st.session_state["superfinal"] = undo_last_superfinal_win(sf)
                    save_current_tournament()
                    st.rerun()

            sf = st.session_state.get("superfinal")
            if sf["games"]:
                st.write("История игр суперфинала:")
                for i, g in enumerate(sf["games"], start=1):
                    winner_name = sf["player_upper"]["full_name"] if g == "upper" else sf["player_lower"]["full_name"]
                    st.write(f"{i}. {winner_name}")

    # -------------------------
    # Итоговые места
    # -------------------------
    sf = st.session_state.get("superfinal")
    if sf is not None and sf["status"] == "done":
        st.markdown("---")
        st.markdown("## Итоговые места")

        places_df = build_places_df()
        st.dataframe(places_df, use_container_width=True)
        if not places_df.empty:
            st.markdown("### Призовые места")
            for _, row in places_df.iterrows():
                st.write(f"**{int(row['place'])} место** — {row['full_name']}")
        st.success(f"Победитель турнира: {sf['winner']['full_name']}")

    # -------------------------
    # История турнира
    # -------------------------
    st.markdown("---")
    st.markdown("## История турнира")

    history_df = build_match_history(
        st.session_state.get("upper_rounds", []),
        st.session_state.get("lower_rounds", []),
        st.session_state.get("superfinal", None),
    )

    if not history_df.empty:
        st.subheader("Все матчи")
        st.dataframe(history_df, use_container_width=True)

        csv_data = history_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Скачать историю матчей CSV",
            data=csv_data,
            file_name=f"match_history_{st.session_state.get('selected_category_for_matches', 'tournament')}.csv",
            mime="text/csv",
        )
    else:
        st.write("История матчей пока пуста.")

    elimination_df = build_elimination_history(st.session_state.get("eliminated_players", []))
    if not elimination_df.empty:
        st.subheader("Порядок выбывания")
        st.dataframe(elimination_df, use_container_width=True)
else:
    st.markdown("### Турнир пока не загружен")
    st.write("Выбери категорию слева и создай новый турнир или загрузи существующий.")
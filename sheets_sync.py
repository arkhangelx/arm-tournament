from __future__ import annotations

import gspread
import pandas as pd

from google.oauth2.service_account import Credentials

from config import (
    SPREADSHEET_URL,
    RAW_SHEET_NAME,
    CLEAN_SHEET_NAME,
)
from categories import normalize_gender, parse_weight, get_weight_class


import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_client():
    credentials = Credentials.from_service_account_info(
        dict(st.secrets["google"]),
        scopes=SCOPES,
    )
    return gspread.authorize(credentials)


def open_spreadsheet():
    gc = get_client()
    return gc.open_by_url(SPREADSHEET_URL)


def get_or_create_worksheet(spreadsheet, title: str, rows: int = 100, cols: int = 20):
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
    return ws


def clear_and_write_dataframe(ws, df: pd.DataFrame):
    ws.clear()

    if df.empty:
        ws.update("A1", [list(df.columns)])
        return

    values = [list(df.columns)] + df.astype(str).fillna("").values.tolist()
    ws.update("A1", values)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    original_cols = list(df.columns)
    col_map = {}

    for col in original_cols:
        c = str(col).strip().lower()

        if "timestamp" in c or "время" in c or "дата" in c:
            col_map[col] = "timestamp"
        elif "фи" in c or "имя" in c or "фам" in c:
            col_map[col] = "full_name"
        elif "пол" in c:
            col_map[col] = "gender_raw"
        elif "вес" in c:
            col_map[col] = "weight_raw"
        elif "факульт" in c:
            col_map[col] = "faculty"

    df = df.rename(columns=col_map)

    required = ["full_name", "gender_raw", "weight_raw", "faculty"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Не удалось найти обязательные столбцы формы: {missing}. Проверь названия колонок в Google Sheet."
        )

    if "timestamp" not in df.columns:
        df["timestamp"] = ""

    return df


def load_raw_responses() -> pd.DataFrame:
    spreadsheet = open_spreadsheet()
    ws = spreadsheet.worksheet(RAW_SHEET_NAME)

    records = ws.get_all_records()
    df = pd.DataFrame(records)

    if df.empty:
        return pd.DataFrame(
            columns=["timestamp", "full_name", "gender_raw", "weight_raw", "faculty"]
        )

    df = normalize_columns(df)
    return df


def build_clean_participants(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw.empty:
        return pd.DataFrame(
            columns=[
                "id",
                "timestamp",
                "full_name",
                "gender",
                "weight_raw",
                "weight",
                "faculty",
                "weight_class",
                "category_key",
                "is_valid",
                "comment",
            ]
        )

    df = df_raw.copy()

    df["full_name"] = df["full_name"].astype(str).str.strip()
    df["faculty"] = df["faculty"].astype(str).str.strip()
    df["gender"] = df["gender_raw"].apply(normalize_gender)
    df["weight"] = df["weight_raw"].apply(parse_weight)

    comments = []
    weight_classes = []
    category_keys = []
    valid_flags = []

    for _, row in df.iterrows():
        comment_parts = []

        if not row["full_name"] or row["full_name"].lower() == "nan":
            comment_parts.append("Пустое ФИ")

        if row["gender"] not in {"M", "W"}:
            comment_parts.append("Некорректный пол")

        if row["weight"] is None:
            comment_parts.append("Некорректный вес")

        if not row["faculty"] or row["faculty"].lower() == "nan":
            comment_parts.append("Пустой факультет")

        if not comment_parts:
            wc, ck = get_weight_class(row["gender"], row["weight"])
            weight_classes.append(wc)
            category_keys.append(ck)
            valid_flags.append(True)
            comments.append("")
        else:
            weight_classes.append("")
            category_keys.append("")
            valid_flags.append(False)
            comments.append("; ".join(comment_parts))

    df["weight_class"] = weight_classes
    df["category_key"] = category_keys
    df["is_valid"] = valid_flags
    df["comment"] = comments

    df = df.reset_index(drop=True)
    df["sort_idx"] = df.index
    df = df.sort_values("sort_idx")
    df = df.drop_duplicates(subset=["full_name", "faculty"], keep="last")

    df = df.reset_index(drop=True)
    df["id"] = [f"P{str(i + 1).zfill(3)}" for i in range(len(df))]

    return df[
        [
            "id",
            "timestamp",
            "full_name",
            "gender",
            "weight_raw",
            "weight",
            "faculty",
            "weight_class",
            "category_key",
            "is_valid",
            "comment",
        ]
    ]


def build_category_sheets(clean_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    result = {}

    valid_df = clean_df[clean_df["is_valid"] == True].copy()

    if valid_df.empty:
        return result

    for category_key, group in valid_df.groupby("category_key"):
        category_df = group[
            ["id", "full_name", "weight", "faculty", "weight_class"]
        ].copy()

        category_df["losses"] = 0
        category_df["status"] = "registered"

        category_df = category_df.sort_values(by=["weight", "full_name"]).reset_index(drop=True)
        result[category_key] = category_df

    return result


def sync_all():
    spreadsheet = open_spreadsheet()

    raw_df = load_raw_responses()
    clean_df = build_clean_participants(raw_df)
    category_sheets = build_category_sheets(clean_df)

    clean_ws = get_or_create_worksheet(spreadsheet, CLEAN_SHEET_NAME, rows=500, cols=20)
    clear_and_write_dataframe(clean_ws, clean_df)

    created_or_updated = []
    for sheet_name, category_df in category_sheets.items():
        ws = get_or_create_worksheet(spreadsheet, sheet_name, rows=500, cols=20)
        clear_and_write_dataframe(ws, category_df)
        created_or_updated.append(sheet_name)

    return {
        "raw_count": len(raw_df),
        "clean_count": len(clean_df),
        "valid_count": int(clean_df["is_valid"].sum()) if not clean_df.empty else 0,
        "invalid_count": int((~clean_df["is_valid"]).sum()) if not clean_df.empty else 0,
        "category_sheets": created_or_updated,
        "clean_df": clean_df,
    }

def clear_participant_data(clear_raw: bool = False):
    spreadsheet = open_spreadsheet()

    worksheets = spreadsheet.worksheets()
    for ws in worksheets:
        title = ws.title
        if title == CLEAN_SHEET_NAME or title.startswith("M_") or title.startswith("W_"):
            ws.clear()

    if clear_raw:
        spreadsheet.worksheet(RAW_SHEET_NAME).clear()

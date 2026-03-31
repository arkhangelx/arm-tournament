import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Test", layout="wide")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1kuJ609rOK-G8mn1mG935W8QswqbsHov7o02GDcCss48/edit?usp=sharing"

st.title("Проверка запуска")

st.write("1. Приложение стартовало")

try:
    creds_dict = dict(st.secrets["google"])
    st.write("2. Secrets прочитаны")

    credentials = Credentials.from_service_account_info(
        creds_dict,
        scopes=SCOPES,
    )
    st.write("3. Credentials созданы")

    gc = gspread.authorize(credentials)
    st.write("4. Авторизация gspread прошла")

    sh = gc.open_by_url(SPREADSHEET_URL)
    st.write("5. Таблица открыта")

    worksheets = sh.worksheets()
    st.write("6. Листы получены")
    st.success([ws.title for ws in worksheets])

except Exception as e:
    st.error(f"Ошибка: {e}")

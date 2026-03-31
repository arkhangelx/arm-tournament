import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1kuJ609rOK-G8mn1mG935W8QswqbsHov7o02GDcCss48/edit?usp=sharing"

st.write("Старт приложения")

try:
    credentials = Credentials.from_service_account_info(
        dict(st.secrets["google"]),
        scopes=SCOPES,
    )
    st.write("Secrets прочитаны")

    gc = gspread.authorize(credentials)
    st.write("gspread авторизован")

    sh = gc.open_by_url(SPREADSHEET_URL)
    st.write("Таблица открыта:", sh.title)

except Exception as e:
    st.error(str(e))

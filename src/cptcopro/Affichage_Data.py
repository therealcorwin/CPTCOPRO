import pandas as pd
import streamlit as st
import sqlite3
from loguru import logger
from pathlib import Path
import os

logger.remove()
logger = logger.bind(type_log="AFFICHAGE")

DB_PATH = os.path.join(os.path.dirname(__file__), "BDD", "copropriete.sqlite")
CSV_PATH = Path(__file__).with_name("test_file.csv")

# ouvrir la connexion avec un context manager pour s'assurer de la fermeture
with sqlite3.connect(str(DB_PATH)) as conn:
    df = pd.read_sql_query("select * from charge", conn)

df.to_csv(CSV_PATH, index=False)

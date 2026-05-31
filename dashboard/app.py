import logging
import os

import streamlit as st
import dotenv

dotenv.load_dotenv()

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

st.set_page_config(page_title="Finance Dashboard", layout="wide", page_icon=":bar_chart:")

overview     = st.Page("pages/overview.py",     title="Overview",     icon="💰️")
expenses     = st.Page("pages/expenses.py",     title="Expenses",     icon="💸")
income       = st.Page("pages/income.py",       title="Income",       icon="💷")
transactions = st.Page("pages/transactions.py", title="Transactions", icon="🧾")

pg = st.navigation([overview, expenses, income, transactions], position="top")

headers = st.context.headers
user  = headers.get("X-Auth-Request-User")
email = headers.get("X-Auth-Request-Email")

# with st.sidebar:
#     if user or email:
#         st.caption(f"Signed in as **{user or email}**")
#         if email and email != user:
#             st.caption(email)
#     else:
#         st.caption("Welcome, guest")

pg.run()

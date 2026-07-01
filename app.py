import streamlit as st
import json
from datetime import datetime

st.set_page_config(
    page_title="M&A Daily Deals Tracker",
    page_icon="⌬",
    layout="wide"
)

st.title("⌬ M&A Daily Deals Tracker")
st.caption("Global mega-deals ($1B+) — updated daily")

st.divider()

def load_deals():
    with open("data/deals.json", "r") as f:
        return json.load(f)

deals = load_deals()

total_deals = len(deals)
values = []
for deal in deals:
    v = deal["value"].replace("$", "").replace("B", "")
    values.append(float(v))
total_value = sum(values)
sectors = [deal["sector"] for deal in deals]
top_sector = max(set(sectors), key=sectors.count)

col1, col2, col3 = st.columns(3)
col1.metric("Total Deals Today", total_deals)
col2.metric("Total Deal Value", f"${total_value:.1f}B")
col3.metric("Top Sector", top_sector)

st.divider()

st.subheader("Filter by Sector")
all_sectors = ["All"] + sorted(list(set(sectors)))
selected_sector = st.selectbox("Select a sector", all_sectors, label_visibility="collapsed")

if selected_sector == "All":
    filtered_deals = deals
else:
    filtered_deals = [d for d in deals if d["sector"] == selected_sector]

st.divider()

st.subheader("Today's Deals")

for deal in filtered_deals:
    with st.expander(f"🏢 {deal['acquirer']} acquires {deal['target']} — {deal['value']}"):
        col1, col2, col3 = st.columns(3)
        col1.write(f"**Sector:** {deal['sector']}")
        col2.write(f"**Geography:** {deal['geography']}")
        col3.write(f"**Date:** {deal['date']}")
        st.write(f"**Strategic Rationale:** {deal['rationale']}")
        st.write(f"**Key Risk:** {deal['key_risk']}")
        st.markdown(f"[View Source]({deal['source_url']})")

st.divider()
st.caption(f"Last updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
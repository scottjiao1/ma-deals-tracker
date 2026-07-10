import streamlit as st  # import and rename library to build web dashboard
import json  # lets python read and write JSON files
import subprocess  # lets python launch and run other scripts (fetcher/prefilter/extractor)
import time  # used for cooldown timing and pipeline progress pacing
from datetime import datetime  # gives access to current date and time

st.set_page_config(
    page_title="M&A Daily Deals Tracker",
    page_icon="⌬",
    layout="wide"
)  # configures browser tab with title, icon, and layout for the Streamlit app

# ─── SESSION STATE SETUP ──────────────────────────────────────────────
if "last_refresh_time" not in st.session_state:
    st.session_state.last_refresh_time = 0

if "pipeline_running" not in st.session_state:
    st.session_state.pipeline_running = False  # tracks if a refresh is actively in progress

st.title("⌬ M&A Daily Deals Tracker")
st.caption("Global mega-deals ($1B+) — reflects the last 7 days")

st.divider()

# ─── REFRESH BUTTON ───────────────────────────────────────────────────
COOLDOWN_SECONDS = 60

time_since_last_refresh = time.time() - st.session_state.last_refresh_time
cooldown_active = time_since_last_refresh < COOLDOWN_SECONDS

# button is disabled if EITHER the cooldown is active OR a pipeline run
# is currently in progress — this second flag closes the timing gap
button_disabled = cooldown_active or st.session_state.pipeline_running

refresh_col, status_col = st.columns([1, 3])

with refresh_col:
    refresh_clicked = st.button(
        "🔄 Refresh Data",
        disabled=button_disabled
    )

with status_col:
    if st.session_state.pipeline_running:
        st.markdown("⚙️ **Refresh in progress...**")
    elif cooldown_active:
        seconds_left = int(COOLDOWN_SECONDS - time_since_last_refresh)
        st.markdown(f"⏳ **On cooldown — available in {seconds_left}s**")
    else:
        st.markdown("✅ **Ready to refresh**")

if refresh_clicked and not button_disabled:
    # set the running flag IMMEDIATELY, before anything else executes —
    # this is what actually closes the double-click gap, since the very
    # next thing that happens is st.rerun(), which redraws the button
    # as disabled before any pipeline work even starts
    st.session_state.pipeline_running = True
    st.rerun()

# this block runs on the RERUN triggered above — pipeline_running is
# already True by this point, so the button is already shown disabled
# to the user before this expensive work even begins
if st.session_state.pipeline_running and not refresh_clicked:
    progress_bar = st.progress(0, text="Fetching latest M&A articles...")

    try:
        subprocess.run(["python3", "fetcher.py"], check=True)
        progress_bar.progress(33, text="Filtering and deduplicating...")

        subprocess.run(["python3", "prefilter.py"], check=True)
        progress_bar.progress(66, text="Extracting deal data with Claude...")

        subprocess.run(["python3", "extractor.py"], check=True)
        progress_bar.progress(100, text="Done!")

    except subprocess.CalledProcessError as e:
        st.error(f"Pipeline step failed: {e}")

    st.session_state.last_refresh_time = time.time()
    st.session_state.pipeline_running = False

    time.sleep(1)
    st.rerun()

elif cooldown_active:
    progress_fraction = time_since_last_refresh / COOLDOWN_SECONDS
    seconds_left = int(COOLDOWN_SECONDS - time_since_last_refresh)
    st.progress(
        progress_fraction,
        text=f"Refresh available in {seconds_left}s"
    )

elif cooldown_active:
    progress_fraction = time_since_last_refresh / COOLDOWN_SECONDS
    seconds_left = int(COOLDOWN_SECONDS - time_since_last_refresh)
    st.progress(
        progress_fraction,
        text=f"Refresh available in {seconds_left}s"
    )

# ─── STOP HERE IF A REFRESH IS ACTIVELY RUNNING ───────────────────────
# rather than adding a "disabled" check to every individual widget below
# (filter, sort, each expander), it's simpler and safer to just not
# render that entire section at all while the pipeline is running — this
# guarantees there's nothing left to click that could interrupt the
# in-progress subprocess calls happening above
if st.session_state.pipeline_running:
    st.info("Deal data is being refreshed. Filters and deal details will be available again shortly.")
    st.stop()


def load_deals():
    with open("data/deals.json", "r") as f:
        return json.load(f)

def load_deals():
    # opens deals.json in read mode and parses it into a Python list of dicts
    with open("data/deals.json", "r") as f:
        return json.load(f)


deals = load_deals()  # calls the function above, stores result

# --- Handle empty state (Day 5 error-handling item, worth guarding now) ---
if not deals:
    st.warning("No $1B+ deals found in the latest data. Try refreshing, or check back later.")
    st.stop()  # halts execution here so nothing below tries to run on an empty list

# ─── STATS BAR (larger, centered, boxed) ──────────────────────────────
total_deals = len(deals)

# use value_billions (a clean float already computed by extractor.py)
# instead of parsing the "value" string, since real deal values look like
# "$10 billion" or "€3.9 billion" — not the "$2.1B" format the old mock
# data used, so string-parsing them would crash
values = [deal.get("value_billions", 0) for deal in deals]
total_value = sum(values)

sectors = [deal["sector"] for deal in deals]
top_sector = max(set(sectors), key=sectors.count)  # most frequent sector

st.markdown(
    f"""
    <div style="
        border: 1px solid #444;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        font-size: 20px;
        margin-bottom: 10px;
    ">
        <strong>{total_deals}</strong> deals this week &nbsp;·&nbsp;
        <strong>${total_value:.1f}B</strong> total value &nbsp;·&nbsp;
        Top sector: <strong>{top_sector}</strong>
    </div>
    """,
    unsafe_allow_html=True
)

st.divider()

# ─── SECTOR FILTER + SORT ─────────────────────────────────────────────
st.subheader("Filter & Sort")

filter_col, sort_col = st.columns(2)

with filter_col:
    all_sectors = ["All"] + sorted(list(set(sectors)))
    selected_sector = st.selectbox("Filter by Sector", all_sectors)

with sort_col:
    sort_option = st.selectbox(
        "Sort by",
        ["Deal Value (High to Low)", "Deal Value (Low to High)", "Date (Newest First)", "Date (Oldest First)"]
    )

if selected_sector == "All":
    filtered_deals = deals
else:
    filtered_deals = [d for d in deals if d["sector"] == selected_sector]

# apply sort based on dropdown selection
# key=lambda d: d.get(...) tells sorted() what value to compare for each
# deal, since you can't directly compare two dictionaries
if sort_option == "Deal Value (High to Low)":
    filtered_deals = sorted(filtered_deals, key=lambda d: d.get("value_billions", 0), reverse=True)
elif sort_option == "Deal Value (Low to High)":
    filtered_deals = sorted(filtered_deals, key=lambda d: d.get("value_billions", 0))
elif sort_option == "Date (Newest First)":
    filtered_deals = sorted(filtered_deals, key=lambda d: d.get("date", ""), reverse=True)
elif sort_option == "Date (Oldest First)":
    filtered_deals = sorted(filtered_deals, key=lambda d: d.get("date", ""))

st.divider()

# ─── DEAL CARDS ───────────────────────────────────────────────────────
st.subheader("This Week's Deals")

for deal in filtered_deals:
    acquirer = deal.get("acquirer", "Unknown")
    target = deal.get("target", "Unknown")
    value = deal.get("value", "Undisclosed")
    mentions = deal.get("mention_count", 1)

    # larger, bolder title using markdown header syntax instead of the
    # default expander font size — status icon removed since all deals
    # currently in the dataset are "Announced" and showing that on every
    # card added no useful signal
    with st.expander(f"🏢  {acquirer} acquires {target} — {value}"):
        st.markdown(f"### {acquirer} → {target}")
        st.markdown(f"#### {value}  ·  📰 {mentions} source{'s' if mentions != 1 else ''}")

        col1, col2, col3 = st.columns(3)
        col1.write(f"**Sector:** {deal.get('sector', 'Unknown')}")
        col2.write(f"**Geography:** {deal.get('geography', 'Unknown')}")
        col3.write(f"**Date:** {deal.get('date', 'Unknown')}")

        st.write(f"**Strategic Rationale:** {deal.get('rationale', 'N/A')}")
        st.write(f"**Key Risk:** {deal.get('key_risk', 'N/A')}")

        if deal.get("why_it_matters"):
            st.write(f"**Why It Matters:** {deal['why_it_matters']}")

        source_list = deal.get("source_list", [])
        if len(source_list) > 1:
            st.caption(f"Reported by: {', '.join(source_list)}")

        st.markdown(f"[View Source]({deal.get('source_url', '#')})")

st.divider()
st.caption(
    f"Last updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
)
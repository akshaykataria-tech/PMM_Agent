
import streamlit as st
import pandas as pd
import numpy as np
import re
from pathlib import Path

st.set_page_config(page_title="Foundit Profiles Q&A", layout="wide")
st.title("Foundit Profiles Q&A (Registered vs Sourced)")

st.write("Upload the **same Excel factsheet** used here (sheet names must match). Ask questions in plain English.")

uploaded = st.file_uploader("Upload 'Factsheet - Sample data.xlsx'", type=["xlsx"])

@st.cache_data
def load_metrics(xlfile):
    xl = pd.ExcelFile(xlfile)
    df_overall = pd.read_excel(xl, sheet_name="India - Overall")
    raw_bfsi   = pd.read_excel(xl, sheet_name="India - BFSI", header=None)
    raw_retail = pd.read_excel(xl, sheet_name="India - Retail", header=None)
    raw_it     = pd.read_excel(xl, sheet_name="India - IT", header=None)

    def extract_overall_metrics(df):
        d = {}
        for _,row in df.iterrows():
            key = str(row.iloc[0]).strip()
            d[key] = pd.to_numeric(row.iloc[1], errors='coerce')
        return d

    def extract_top_metrics(raw_df):
        rows = []
        for i in range(len(raw_df)):
            key = raw_df.iloc[i,0]
            val = raw_df.iloc[i,1] if raw_df.shape[1] > 1 else np.nan
            if pd.isna(key):
                break
            rows.append((str(key).strip(), pd.to_numeric(val, errors='coerce')))
        return dict(rows)

    def normalize(d):
        mapping = {
            '12M Active (Reg) Profiles': '12M Active Profiles',
            '6M Active  (Reg) Profiles': '6M Active Profiles',
            '6M Reg': '6M Registered'
        }
        return { mapping.get(k,k): v for k,v in d.items() }

    metrics_overall = normalize(extract_overall_metrics(df_overall))
    metrics_bfsi    = normalize(extract_top_metrics(raw_bfsi))
    metrics_retail  = normalize(extract_top_metrics(raw_retail))
    metrics_it      = normalize(extract_top_metrics(raw_it))

    # Build tidy
    records = []
    for name, d in [
        ("India (Overall)", metrics_overall),
        ("BFSI", metrics_bfsi),
        ("Retail", metrics_retail),
        ("IT", metrics_it),
    ]:
        rec = {
            "Segment": name,
            "Total Profiles": d.get("Total Profiles", np.nan),
            "All time Sourced": d.get("All time sourced", np.nan),
            "All time Registered": d.get("All time Registered", np.nan),
            "12M Sourced": d.get("12M Sourced", np.nan),
            "12M Registered": d.get("12M Registered", np.nan),
            "12M Active Profiles": d.get("12M Active Profiles", np.nan),
            "6M Sourced": d.get("6M Sourced", np.nan),
            "6M Registered": d.get("6M Registered", np.nan),
            "6M Active Profiles": d.get("6M Active Profiles", np.nan),
        }
        s = rec["All time Sourced"]
        r = rec["All time Registered"]
        t = rec["Total Profiles"]
        rec["% Registered (all-time)"] = (r / t) if (t and t>0) else np.nan
        rec["% Sourced (all-time)"] = (s / t) if (t and t>0) else np.nan
        records.append(rec)

    df = pd.DataFrame.from_records(records)
    order = ["Segment","Total Profiles","All time Sourced","All time Registered",
             "% Registered (all-time)","% Sourced (all-time)",
             "12M Sourced","12M Registered","12M Active Profiles",
             "6M Sourced","6M Registered","6M Active Profiles"]
    df = df[order]
    return df

def find_segment(text):
    text_l = text.lower()
    if "bfsi" in text_l:
        return "BFSI"
    if "retail" in text_l:
        return "Retail"
    if re.search(r"\bit\b", text_l) and "retail" not in text_l and "bfsi" not in text_l:
        return "IT"
    # default overall
    if "overall" in text_l or "india" in text_l:
        return "India (Overall)"
    return None

def find_metric(text):
    text_l = text.lower()
    # priorities for specificity
    if "12m" in text_l or "last 12" in text_l or "past 12" in text_l or "twelve" in text_l:
        if "register" in text_l:
            return "12M Registered"
        if "source" in text_l:
            return "12M Sourced"
        if "active" in text_l:
            return "12M Active Profiles"
    if "6m" in text_l or "last 6" in text_l or "past 6" in text_l or "six months" in text_l:
        if "register" in text_l:
            return "6M Registered"
        if "source" in text_l:
            return "6M Sourced"
        if "active" in text_l:
            return "6M Active Profiles"
    if "total" in text_l and "profile" in text_l:
        return "Total Profiles"
    if "all time" in text_l or "all-time" in text_l or "lifetime" in text_l:
        if "register" in text_l:
            return "All time Registered"
        if "source" in text_l:
            return "All time Sourced"
    # generic fallbacks
    if "register" in text_l:
        return "All time Registered"
    if "source" in text_l:
        return "All time Sourced"
    if "active" in text_l:
        return "12M Active Profiles"
    return None

def wants_percentage(text):
    return any(x in text.lower() for x in ["percent", "percentage", "share", "%"])

example_qs = [
    "How many registered profiles in IT?",
    "What's the all-time sourced count for BFSI?",
    "Share of registered vs sourced overall",
    "12M registered in Retail",
    "Compare 6M registered vs 6M sourced in IT",
    "Total profiles in India overall",
]

if uploaded is not None:
    df = load_metrics(uploaded)
    st.subheader("Parsed Summary")
    st.dataframe(df, use_container_width=True)

    st.markdown("**Try a question:**")
    cols = st.columns(len(example_qs))
    for i,q in enumerate(example_qs):
        if cols[i].button(q, key=f"q{i}"):
            st.session_state["nlq"] = q

    query = st.text_input("Ask a question", value=st.session_state.get("nlq", ""))

    if query.strip():
        seg = find_segment(query) or "India (Overall)"
        metric = find_metric(query)

        if "compare" in query.lower() or ("vs" in query.lower() and "vs." not in query.lower()):
            # simple compare logic: registered vs sourced in the chosen timeframe (6M/12M/all-time)
            timeframe_metric_r = None
            timeframe_metric_s = None
            if "12m" in query.lower():
                timeframe_metric_r = "12M Registered"
                timeframe_metric_s = "12M Sourced"
            elif "6m" in query.lower():
                timeframe_metric_r = "6M Registered"
                timeframe_metric_s = "6M Sourced"
            else:
                timeframe_metric_r = "All time Registered"
                timeframe_metric_s = "All time Sourced"

            row = df[df["Segment"]==seg]
            if len(row)==1:
                r = float(row[timeframe_metric_r])
                s = float(row[timeframe_metric_s])
                st.write(f"**{seg} — {timeframe_metric_r} vs {timeframe_metric_s}:** {int(r):,} vs {int(s):,}")
                if s > 0:
                    ratio = r/s
                    st.write(f"Registered-to-Sourced ratio: {ratio:.2f}")
                st.bar_chart(pd.DataFrame({
                    timeframe_metric_r: [r],
                    timeframe_metric_s: [s]
                }), use_container_width=True)
            else:
                st.warning("Couldn't find the requested segment.")
        elif metric is not None:
            row = df[df["Segment"]==seg]
            if len(row)==1:
                val = float(row[metric])
                if wants_percentage(query) and metric in ["All time Registered","All time Sourced"]:
                    denom = float(row["Total Profiles"])
                    pct = (val/denom*100.0) if denom>0 else np.nan
                    st.write(f"**{seg} — {metric} (% of total):** {val:,.0f} ({pct:.1f}%)")
                else:
                    st.write(f"**{seg} — {metric}:** {val:,.0f}")
            else:
                st.warning("Couldn't find the requested segment.")
        else:
            # generic overview for a segment
            row = df[df["Segment"]==seg]
            if len(row)==1:
                sub = row[["All time Registered","All time Sourced","Total Profiles","% Registered (all-time)","% Sourced (all-time)"]].T
                sub.columns = [seg]
                st.dataframe(sub)
                st.bar_chart(row[["All time Registered","All time Sourced"]].T, use_container_width=True)
            else:
                st.warning("Please specify BFSI, Retail, IT, or Overall.")
else:
    st.info("Upload the Excel file to begin.")

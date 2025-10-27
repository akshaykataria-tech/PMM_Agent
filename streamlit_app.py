
import streamlit as st
import pandas as pd
import numpy as np
import re
from io import BytesIO
from supabase import create_client, Client

st.set_page_config(page_title="Foundit Profiles Q&A — Full (Supabase-backed)", layout="wide")
st.title("Foundit Profiles Q&A — Full (Supabase-backed)")

# ----------------------
# Secrets & configuration
# ----------------------
SB_URL   = st.secrets.get("SUPABASE_URL")
SB_KEY   = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or st.secrets.get("SUPABASE_ANON_KEY")
BUCKET   = st.secrets.get("SUPABASE_BUCKET", "foundit-factsheets")
OBJECT   = st.secrets.get("SUPABASE_OBJECT_PATH", "factsheet/latest.xlsx")
ADMIN_PW = st.secrets.get("ADMIN_PASS")

if not (SB_URL and SB_KEY):
    st.error("Missing SUPABASE_URL and key in st.secrets. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY).")
    st.stop()

supabase: Client = create_client(SB_URL, SB_KEY)

st.sidebar.header("Data source")
st.sidebar.write(f"Supabase Storage → `{BUCKET}/{OBJECT}`")
st.button("🔄 Refresh data", on_click=lambda: st.cache_data.clear())

# ----------------------
# Storage helpers
# ----------------------
def supa_download_bytes(bucket: str, path: str) -> bytes | None:
    try:
        data = supabase.storage.from_(bucket).download(path)
        return data
    except Exception as e:
        st.warning(f"Download failed or object not found: {e}")
        return None

def supa_upload_file(bucket: str, path: str, uploaded_file) -> tuple[bool, str | None]:
    try:
        uploaded_file.seek(0)
        file_opts = {
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "upsert": "true",
        }
        supabase.storage.from_(bucket).upload(path=path, file=uploaded_file, file_options=file_opts)
        return True, None
    except Exception as e:
        return False, str(e)

# ----------------------
# Admin upload UI
# ----------------------
with st.expander("🔐 Admin: Upload/replace Excel in Supabase Storage", expanded=False):
    if ADMIN_PW:
        pwd = st.text_input("Admin password", type="password")
        if pwd == ADMIN_PW:
            new_file = st.file_uploader("Upload new Excel (.xlsx) to replace the current factsheet", type=["xlsx"])
            if new_file and st.button("Upload to Supabase"):
                ok, err = supa_upload_file(BUCKET, OBJECT, new_file)
                if ok:
                    st.success("Uploaded. Click **Refresh data** to reload.")
                    st.cache_data.clear()
                else:
                    st.error(f"Upload failed: {err}")
        else:
            st.caption("Enter admin password to enable upload.")
    else:
        st.caption("Set ADMIN_PASS in st.secrets to enable admin uploads.")

# ----------------------
# Load Excel from Supabase
# ----------------------
@st.cache_data(ttl=60)
def load_excel_from_supabase(bucket: str, path: str):
    content = supa_download_bytes(bucket, path)
    if not content:
        return None
    return pd.ExcelFile(BytesIO(content), engine="openpyxl")

xl = load_excel_from_supabase(BUCKET, OBJECT)
if xl is None:
    st.stop()

# ----------------------
# Parsing
# ----------------------
HEADLINE_SHEETS = ["India - Overall"]
SEGMENT_SHEETS = {"BFSI": "India - BFSI", "Retail": "India - Retail", "IT": "India - IT"}

def normalize_columns(df):
    rename_map = {
        "6M Reg": "6M Registered",
        "6M Active  (Reg) Profiles": "6M Active Profiles",
        "12M Active (Reg) Profiles": "12M Active Profiles",
    }
    return df.rename(columns=rename_map)

def parse_dimension_blocks(raw_df):
    """
    Detect 'By <Dimension>' blocks like:
    Row r:   [ 'By Gender', 'Total Profiles', 'All time sourced', 'All time Registered', ... ]
    Row r+1: [ 'Male', <numbers> ... ]
    Continue until a blank row or a new 'By ' section or 'Percentage' marker.
    Returns dict[dimension] -> tidy DataFrame
    """
    blocks = {}
    i = 0
    n = len(raw_df)
    while i < n:
        cell0 = raw_df.iloc[i, 0]
        if isinstance(cell0, str) and cell0.strip().lower().startswith("by "):
            dim = cell0.strip()[3:].strip()  # remove 'By '
            # collect col headers from same row (cells 1..k)
            cols = [raw_df.iloc[i, 0]]
            j = 1
            while j < raw_df.shape[1]:
                v = raw_df.iloc[i, j]
                if pd.isna(v):
                    break
                cols.append(str(v).strip())
                j += 1

            # data rows
            data = []
            r = i + 1
            while r < n:
                first = raw_df.iloc[r, 0]
                if pd.isna(first):
                    break
                if isinstance(first, str) and (first.strip().lower().startswith("by ") or first.strip().lower()=="percentage"):
                    break
                row_vals = [first]
                for c in range(1, len(cols)):
                    row_vals.append(pd.to_numeric(raw_df.iloc[r, c], errors='coerce'))
                data.append(row_vals)
                r += 1

            if data and len(cols) > 1:
                clean_dim = dim.replace(":", "").replace("-", " ").strip().title()
                headers = [clean_dim] + cols[1:]
                df_block = pd.DataFrame(data, columns=headers)
                df_block = normalize_columns(df_block)
                # Drop rows where the category is NaN
                df_block = df_block[df_block[clean_dim].notna()].reset_index(drop=True)
                blocks[clean_dim] = df_block
            i = r
        else:
            i += 1
    return blocks

# Parse headline metrics
headline = {}
for sh in HEADLINE_SHEETS:
    try:
        tmp = pd.read_excel(xl, sheet_name=sh)
        d = {}
        for _, row in tmp.iterrows():
            key = str(row.iloc[0]).strip()
            d[key] = pd.to_numeric(row.iloc[1], errors='coerce')
        headline[sh] = d
    except Exception:
        pass

# Parse all segment sheets (BFSI/Retail/IT)
segment_blocks = {}
for seg, sheet in SEGMENT_SHEETS.items():
    raw = pd.read_excel(xl, sheet_name=sheet, header=None)
    blocks = parse_dimension_blocks(raw)
    segment_blocks[seg] = blocks

# ----------------------
# Explore what's available
# ----------------------
with st.expander("📚 Data dictionary (auto-detected dimensions per segment)", expanded=True):
    for seg, blocks in segment_blocks.items():
        dims = list(blocks.keys())
        if dims:
            st.write(f"**{seg}** → Dimensions: {', '.join(dims)}")
            for dname, dfb in blocks.items():
                st.write(f"- {dname}: {len(dfb)} categories → sample: {', '.join(map(str, dfb[dname].astype(str).head(5)))}")
        else:
            st.write(f"**{seg}** → No 'By <Dimension>' blocks found.")

# ----------------------
# NLQ
# ----------------------
DIM_SYNONYMS = {
    "gender": ["gender", "male", "female", "any"],
    "experience": ["experience", "exp", "yrs", "years", "fresher", "fresher(s)"],
    "location": ["location", "city", "state", "region"],
    "role": ["role", "designation", "title"],
    "sub industry": ["subindustry", "sub-industry", "sub industry", "domain"],
}

def detect_segment(text):
    t = text.lower()
    if "bfsi" in t: return "BFSI"
    if "retail" in t: return "Retail"
    if re.search(r"\bit\b", t) and "retail" not in t and "bfsi" not in t: return "IT"
    # default to overall answers using any one segment? We'll default to 'India - Overall' only for headline metrics
    return None

def detect_timeframe(text):
    t = text.lower()
    if "12m" in t or "last 12" in t or "past 12" in t or "twelve" in t:
        return "12M"
    if "6m" in t or "last 6" in t or "past 6" in t or "six months" in t:
        return "6M"
    return "ALL"

def detect_measure(text):
    t = text.lower()
    if "active" in t: return "Active"
    if "register" in t: return "Registered"
    if "source" in t: return "Sourced"
    if "total" in t and "profile" in t: return "Total Profiles"
    # Default to Registered
    return "Registered"

def detect_dimension(text, available_dims):
    t = text.lower()
    # try explicit 'By <Dim>' phrasing
    m = re.search(r"by\s+([a-zA-Z\- ]+)", t)
    if m:
        cand = m.group(1).strip()
        for dim in available_dims:
            if dim.lower() == cand.lower():
                return dim
    # synonyms
    for dim in available_dims:
        key = dim.lower()
        syns = []
        for base, lst in DIM_SYNONYMS.items():
            if base == key or key.startswith(base):
                syns += lst
        if any(s in t for s in syns) or key in t:
            return dim
    # not found
    return None

def find_category(text, categories):
    t = text.lower()
    # quoted category
    m = re.search(r"['\"]([^'\"]+)['\"]", t)
    if m:
        q = m.group(1).strip().lower()
        for c in categories:
            if c.lower() == q:
                return c
    # direct token contains
    for c in categories:
        if c and c.lower() in t:
            return c
    return None

def metric_column(timeframe, measure):
    if timeframe == "12M":
        if measure == "Registered": return "12M Registered"
        if measure == "Sourced": return "12M Sourced"
        if measure == "Active": return "12M Active Profiles"
    if timeframe == "6M":
        if measure == "Registered": return "6M Registered"
        if measure == "Sourced": return "6M Sourced"
        if measure == "Active": return "6M Active Profiles"
    # ALL time
    if measure == "Registered": return "All time Registered"
    if measure == "Sourced": return "All time Sourced"
    if measure == "Total Profiles": return "Total Profiles"
    # default
    return "All time Registered"

example_qs = [
    "BFSI — registered by gender (12M)",
    "Retail: 6M sourced for 'Female' by gender",
    "IT — registered by experience (all-time)",
    "BFSI — registered for '2-5 Years' by experience (12M)",
    "IT — total profiles",
    "Retail — compare 6M registered vs 6M sourced for 'Female' by gender",
]

st.subheader("Ask a question")
st.caption("Tip: include segment (BFSI/Retail/IT), the dimension (gender/experience/location/role/sub-industry), and optionally a category in quotes like 'Female' or 'Bengaluru'.")
colx = st.columns(len(example_qs))
for i,q in enumerate(example_qs):
    if colx[i].button(q, key=f"x{i}"):
        st.session_state["q"] = q

q = st.text_input("Your question", value=st.session_state.get("q",""))

if q.strip():
    seg = detect_segment(q)
    tf = detect_timeframe(q)
    meas = detect_measure(q)

    if seg is None:
        st.warning("Please specify a segment (BFSI, Retail, or IT).")
    else:
        dims_available = list(segment_blocks.get(seg, {}).keys())
        dim = detect_dimension(q, dims_available)

        if "compare" in q.lower() or (" vs " in q.lower() and "vs." not in q.lower()):
            # Compare Registered vs Sourced for a chosen dimension/category
            if dim is None:
                st.warning(f"No dimension detected. Available for {seg}: {', '.join(dims_available) or 'None'}")
            else:
                dfb = segment_blocks[seg][dim]
                cat = find_category(q, dfb[dim].astype(str).tolist())
                if cat is None:
                    st.warning(f"No category detected for '{dim}'. Example categories: {', '.join(dfb[dim].astype(str).head(5))} ...")
                else:
                    col_r = metric_column(tf, "Registered")
                    col_s = metric_column(tf, "Sourced")
                    if col_r not in dfb.columns or col_s not in dfb.columns:
                        st.error(f"Requested metrics not found in the sheet for {seg}/{dim}.")
                    else:
                        sub = dfb[dfb[dim].astype(str).str.lower()==cat.lower()]
                        if len(sub)==1:
                            r = float(sub.iloc[0][col_r])
                            s = float(sub.iloc[0][col_s])
                            st.write(f"**{seg} — {dim}='{cat}' — {tf} Registered vs Sourced:** {int(r):,} vs {int(s):,}")
                            if s>0:
                                st.write(f"Registered-to-Sourced ratio: {r/s:.2f}")
                            st.bar_chart(pd.DataFrame({col_r:[r], col_s:[s]}), use_container_width=True)
                        else:
                            st.warning("Category match ambiguous.")
        else:
            if dim is None:
                # if no dimension, answer headline metric, or suggest dims
                if detect_measure(q) == "Total Profiles" and seg in headline:
                    val = headline.get("India - Overall", {}).get("Total Profiles")
                    st.write(f"**India (Overall) — Total Profiles:** {int(val):,}" if val else "Total not found in Overall sheet.")
                else:
                    st.info(f"Available dimensions for {seg}: {', '.join(dims_available) or 'None'}. Try: {seg} — registered by gender (12M).")
            else:
                dfb = segment_blocks[seg][dim]
                cat = find_category(q, dfb[dim].astype(str).tolist())
                col = metric_column(tf, meas)

                if col not in dfb.columns and col != "Total Profiles":
                    st.error(f"Requested metric '{col}' not found in {seg}/{dim}. Available: {', '.join(dfb.columns)}")
                else:
                    if cat:
                        sub = dfb[dfb[dim].astype(str).str.lower()==cat.lower()]
                        if len(sub)==1:
                            val = sub.iloc[0].get(col, np.nan)
                            st.write(f"**{seg} — {dim}='{cat}' — {col}:** {0 if pd.isna(val) else int(val):,}")
                        else:
                            st.warning("Category match ambiguous.")
                    else:
                        # No category -> show top N categories by chosen metric
                        metric = col if col in dfb.columns else "All time Registered"
                        tmp = dfb[[dim, metric]].copy()
                        tmp = tmp.sort_values(metric, ascending=False).head(10)
                        st.write(f"**Top {len(tmp)} categories in {seg} by {metric} (dimension: {dim})**")
                        st.dataframe(tmp.reset_index(drop=True), use_container_width=True)
                        st.bar_chart(tmp.set_index(dim), use_container_width=True)


# Foundit Profiles Q&A — Full (Supabase-backed)

**What’s new:** This version parses **every** `'By <Dimension>'` table in each segment sheet, so it can answer questions by **Gender, Experience**, and any other dimensions present in the Excel (e.g., Location, Role, Sub-Industry) with no code changes.

## Setup
1. **Supabase Storage**
   - Create a bucket (private recommended), e.g. `foundit-factsheets`.
   - Choose an object path, e.g. `factsheet/latest.xlsx`.

2. **Streamlit secrets (Manage app → Advanced → Secrets)**
```toml
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "YOUR_SERVICE_ROLE"
SUPABASE_BUCKET = "foundit-factsheets"
SUPABASE_OBJECT_PATH = "factsheet/latest.xlsx"
ADMIN_PASS = "set-a-strong-password"
```

3. **Deploy on Streamlit Cloud**
   - Put `streamlit_app.py` and `requirements.txt` at repo root.
   - Set main file to `streamlit_app.py`. Select Python 3.11/3.12. Deploy.
   - Open the app → **Admin** → Upload Excel once. Then it loads from Supabase for everyone.

## Ask in plain English
Examples:
- `BFSI — registered by gender (12M)`
- `Retail: 6M sourced for 'Female' by gender`
- `IT — registered by experience (all-time)`
- `BFSI — registered for '2-5 Years' by experience (12M)`
- `Retail — compare 6M registered vs 6M sourced for 'Female' by gender`

If your Excel includes new tables like **By Location**, **By Role**, or **By Sub-Industry**, the app will detect them automatically and they’ll become queryable immediately.

## Notes
- The parser expects blocks like:
  - Header row: `By <Dimension> | Total Profiles | All time sourced | All time Registered | ...`
  - Followed by category rows (e.g., Male, Female, Any…), ending at a blank row or another `By ...` block.
- Columns are normalised (e.g., `6M Reg → 6M Registered`, `12M Active (Reg) Profiles → 12M Active Profiles`).


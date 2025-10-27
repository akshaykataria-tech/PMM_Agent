# Foundit Profiles Q&A (Registered vs Sourced)

A tiny Streamlit app that answers natural-language questions about Registered vs Sourced counts from the Foundit factsheet Excel.

## Run locally
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy to Streamlit Community Cloud
1. Push this folder to a public or private GitHub repo.
2. Go to https://streamlit.io/cloud, click **Create app**.
3. Select your repo, branch, and set **Main file path** to `streamlit_app.py`.
4. Click **Deploy**. Upload the Excel in the UI at runtime.

## Deploy to Hugging Face Spaces
1. Create a new **Space** with **SDK = Streamlit**.
2. Upload these files (`streamlit_app.py`, `requirements.txt`).
3. The Space will build and serve automatically. Upload the Excel in the UI.

## Notes
- The app parses these sheets: `India - Overall`, `India - BFSI`, `India - Retail`, `India - IT`.
- No external APIs required; all logic runs in-app.

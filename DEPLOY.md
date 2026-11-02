# Deploying House Planner to Streamlit Community Cloud

Do this once from your laptop. You need: a GitHub account, this repo
pushed to GitHub, and your Meta Model API key. Takes about 10 minutes.

## 0. Before you start (on your laptop)

1. Push the repo to GitHub from your own terminal:
   `git push origin main`
2. Check `.env` is NOT in the repo: open the GitHub page and confirm
   there is no `.env` file listed. (It is git-ignored; the key must
   never be committed.)

## 1. Create the Cloud app

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app** (or **New app**).
3. Pick **Deploy a public app from GitHub** (Community Cloud is free
   for public repos).
4. Under **Repository**, choose your `house-planner` repo.
5. Under **Branch**, choose `main`.
6. Under **Main file path**, type exactly: `app.py`
7. Under **Advanced settings**, set the Python version to **3.13**
   (the version this repo is tested on).
8. Click **Deploy**. The first build installs `requirements.txt` and
   takes a few minutes. The app opens but shows "The AI service is
   not configured" until step 2 is done - that is expected.

## 2. Add the API key in Secrets (never in the code)

1. On your deployed app page, open the app menu (top right) and go to
   **Settings** > **Secrets**.
2. Paste exactly this (your real key, quotes included):
   `META_API_KEY = "your-key-here"`
3. Click **Save**. The app restarts by itself.

## 3. Check it works

1. Open the app link, press **Start planning**, fill any brief
   in the sidebar (or press **Try an example**), enter toilets,
   press **Generate plans**.
2. You should see tabs for options A/B/C, each with a large plan
   drawing plus a narrow side panel; rooms, explanation and the
   checklist sit under the collapsed **Plan details** expander.
3. Press **Render this plan** under one option: an AI top-down
   render appears below the plan. If it fails, the app shows a
   friendly message - re-check step 2 (usually a typo in the key
   or extra spaces).

## Notes

- The app reads the key from Streamlit Secrets first, then from the
  environment (`.env` on your laptop). No code change between the two.
- To update the live app later: push new commits to GitHub - the
  Cloud app rebuilds itself from `main` within minutes.
- Keep the repo public while it runs on the free tier (Community
  Cloud serves public repos free).

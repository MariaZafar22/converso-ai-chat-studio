# Deployment Guide

## 1. Push to GitHub

```bash
cd converso-ai-chat-studio
git init
git add .
git commit -m "feat: Converso AI Chat Studio"
git branch -M main
git remote add origin https://github.com/<your-username>/converso-ai-chat-studio.git
git push -u origin main
```

Create the empty repository first on github.com (no README, no .gitignore). Confirm that `.env` is **not** in the upload.

## 2. Deploy free on Streamlit Community Cloud

1. Go to **share.streamlit.io** and sign in with GitHub.
2. Click **Create app** and select your repository, branch `main`, main file `app.py`.
3. Open **Advanced settings → Secrets** and paste:

   ```toml
   GROQ_API_KEY = "your_real_key"
   ```
4. Click **Deploy**. Your live link looks like `https://<name>.streamlit.app`.

## 3. Alternative: Hugging Face Spaces

Create a Space with the **Streamlit** SDK, upload the files and add the key under **Settings → Secrets**.

## 4. Submit

Paste the GitHub link, LinkedIn post link and live app link into the Codomax form, and tag **Codomax Digital Solutions** in your post.

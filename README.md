# Barista Scheduler / Payouts

A small Flask app that reads Google Calendar events and computes base pay plus card‑tip splits per day and per shift. Built for BRB Coffee / Laundryless operations to keep barista payouts transparent and automated.

---

# Running Locally

## Clone the repo

```bash
git clone <your-repo-url>
cd barista-scheduler/barista-pay
```

---

##  Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\\Scripts\\activate
pip install -r requirements.txt
```

---

##  Create Google Calendar credentials

This app needs permission to read your BRB Coffee shift calendar.

### Steps

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Enable **Google Calendar API**
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth Client ID**
4. Choose **Desktop App**
5. Download the JSON file

Rename and move it into the project folder:

```bash
mv ~/Downloads/client_secret_*.json credentials.json
```

Your folder should now look like:

```
barista-pay/
├── app.py
├── gcal_client.py
├── credentials.json
├── requirements.txt
```

 **Never commit this file to GitHub**
Add to `.gitignore`:

```
credentials.json
token.json
```

---

##  First‑time login

Run once locally to generate `token.json`:

```bash
python app.py
```

A browser will open → log into your Google account → allow Calendar access.

This creates:

```
token.json
```

This file refreshes automatically after that.

---

## Set environment variables

For Austin / BRB Coffee schedule:

```bash
export CALENDAR_ID=primary
export SECRET_KEY=dev
export TZ=America/Chicago
export OPEN_TIME=08:00
export SWITCH_TIME=14:00
export CLOSE_TIME=21:00
```

Then run again:

```bash
python app.py
```

Open → [http://localhost:5000](http://localhost:5000)

---

#  Run with Docker (optional)

```bash
docker build -t barista-pay -f Dockerfile .

docker run -p 8080:8080 \
  -e CALENDAR_ID=primary \
  -e SECRET_KEY=dev \
  -e TZ=America/Chicago \
  -v $(pwd)/credentials.json:/app/credentials.json \
  -v $(pwd)/token.json:/app/token.json \
  barista-pay
```

Open → [http://localhost:8080](http://localhost:8080)

---

#  Troubleshooting

###  FileNotFoundError credentials.json

Make sure the file exists:

```bash
ls credentials.json
```

If missing → download from Google Cloud Console.

---

### Wrong shifts or pay times

Check timezone and shift hours env vars.

---

# Deployment Options

GitHub Pages is not supported (needs backend).

Recommended:

* Google Cloud Run
* Render
* Railway
* Fly.io

Use GitHub Actions to auto‑deploy containers.

---

#  Security Notes

• Never commit `credentials.json` or `token.json`
• Use private calendars
• Rotate tokens if leaked

---

#  Next Improvements (for BRB Coffee)

• Export daily payout CSV
• Auto‑email baristas their tip splits
• Connect POS CSV import
• Admin dashboard for shift edits


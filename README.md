# DBRAIT Repository (foundation)
Runs on your laptop. Python 3.10+.

    pip install -r requirements.txt
    uvicorn app:app --reload

Open http://localhost:8000 . On first run the terminal prints the admin password
(or set ADMIN_PASSWORD before starting). Tests: `pip install pytest && pytest`.

Demo URL for others: `cloudflared tunnel --url http://localhost:8000` (temporary link; stop it when done).
Data lives in dbrait.db and uploads/ — delete both to start fresh.

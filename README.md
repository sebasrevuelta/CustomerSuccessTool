# Customer Health Score Tool
This app reads data from a Google Sheet and displays it in a table.

## Setup

1. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Google Sheets API (service account)**

   - Go to [Google Cloud Console](https://console.cloud.google.com/), create or select a project.
   - Enable the **Google Sheets API** for that project.
   - Under **APIs & Services → Credentials**, create a **Service account** and download its JSON key.
   - Save the JSON file as `credentials.json` in the project root (or set `GOOGLE_CREDENTIALS_PATH` to its path).
   - Share your Google Sheet with the service account email (e.g. `something@project.iam.gserviceaccount.com`) with **Viewer** access.

3. **Configure environment**

   Copy `.env.example` to `.env` and set:

   - `DATABASE_URL`: PostgreSQL SQLAlchemy URL  
     Example: `postgresql+psycopg2://appuser:app_password@127.0.0.1:5432/customer_success`
   - `GOOGLE_SHEET_ID`: the sheet ID from the sheet URL  
     `https://docs.google.com/spreadsheets/d/<GOOGLE_SHEET_ID>/edit`

4. **Run the app locally**

   ```bash
   flask --app app run
   ```

   Open http://127.0.0.1:5000 to see the table. The first row of the sheet is used as the table header.

## Run with Docker

1. **Build the image**

   ```bash
   docker build -t customer-success-tool .
   ```

2. **Run the container**

   ```bash
   docker run --rm -p 5000:5000 -p 5432:5432 \
     --env-file .env \
     -e POSTGRES_DB=customer_success \
     -e POSTGRES_USER=appuser \
     -e POSTGRES_PASSWORD=app_password \
     -v "$(pwd)/credentials.json:/app/credentials.json:ro" \
     customer-success-tool
   ```

3. **Open the app**

   Visit http://127.0.0.1:5000

### Run with demo data (`LOAD_DEMO_DATA=True`)

If you want to start without Google Sheet sync and populate demo rows instead:

1. Set `LOAD_DEMO_DATA=True` in `.env` (or pass `-e LOAD_DEMO_DATA=True` to `docker run`).
2. Start the container normally.

With `LOAD_DEMO_DATA=True`, startup loads sample rows from `customer_success_sample_data.sql` into both `Customer_Success` and `feature_request`.  
With `LOAD_DEMO_DATA=False` (default), startup syncs `Customer_Success` from Google Sheets.

## Sync Google Sheet to PostgreSQL

Run the sync job to read from Google Sheets and upsert into `"Customer_Success"`:

```bash
python src/nurture.py
```
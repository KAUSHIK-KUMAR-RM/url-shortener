import os
import secrets
from urllib import request
from dotenv import load_dotenv
import mysql.connector
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, HttpUrl

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="MySQL URL Shortener API")

# MySQL Configuration
MYSQL_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "url_shortener_db"),
}


def get_db_connection():
    """Returns a new MySQL database connection using env configurations."""
    try:
        connection = mysql.connector.connect(**MYSQL_CONFIG)
        return connection
    except mysql.connector.Error as err:
        raise HTTPException(
            status_code=500, detail=f"Database Connection Error: {err}"
        )


class URLRequest(BaseModel):
    url: HttpUrl


class URLResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str


def generate_short_code(length: int = 6) -> str:
    """Generates a URL-safe random string."""
    return secrets.token_urlsafe(length)[:length]


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    """Serves the simple HTML/JS frontend at root."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>URL Shortener</title>
        <style>
            body {
                font-family: system-ui, -apple-system, sans-serif;
                background-color: #f4f4f9;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .card {
                background: white;
                padding: 2rem;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                width: 100%;
                max-width: 400px;
            }
            h1 { font-size: 1.5rem; margin-bottom: 1rem; color: #333; }
            input[type="url"] {
                width: 100%;
                padding: 0.6rem;
                border: 1px solid #ccc;
                border-radius: 4px;
                box-sizing: border-box;
                margin-bottom: 1rem;
            }
            button {
                width: 100%;
                padding: 0.6rem;
                background-color: #0066cc;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                cursor: pointer;
            }
            button:hover { background-color: #0052a3; }
            .result {
                margin-top: 1rem;
                padding: 0.8rem;
                background: #eef9ff;
                border: 1px solid #b3e5fc;
                border-radius: 4px;
                display: none;
                word-break: break-all;
            }
            .error {
                margin-top: 1rem;
                color: red;
                font-size: 0.9rem;
                display: none;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>URL Shortener</h1>
            <form id="shortenForm">
                <input type="url" id="urlInput" placeholder="https://example.com" required>
                <button type="submit">Shorten URL</button>
            </form>
            <div id="error" class="error"></div>
            <div id="result" class="result">
                Short URL: <br>
                <a id="shortLink" href="#" target="_blank"></a>
            </div>
        </div>

        <script>
            document.getElementById('shortenForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const urlInput = document.getElementById('urlInput').value;
                const resultDiv = document.getElementById('result');
                const errorDiv = document.getElementById('error');
                const shortLink = document.getElementById('shortLink');

                resultDiv.style.display = 'none';
                errorDiv.style.display = 'none';

                try {
                    const response = await fetch('/shorten', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: urlInput })
                    });

                    if (!response.ok) {
                        throw new Error('Please enter a valid URL');
                    }

                    const data = await response.json();
                    shortLink.href = data.short_url;
                    shortLink.textContent = data.short_url;
                    resultDiv.style.display = 'block';
                } catch (err) {
                    errorDiv.textContent = err.message;
                    errorDiv.style.display = 'block';
                }
            });
        </script>
    </body>
    </html>
    """


@app.post("/shorten", response_model=URLResponse, status_code=201)
def shorten_url(payload: URLRequest):
    """
    Accepts a long URL, saves it to MySQL, and returns the short code.
    """
    base_url = str(request.base_url).rstrip("/")
    original_url_str = str(payload.url)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1. Check if original URL already exists in MySQL
        select_query = "SELECT short_code FROM urls WHERE original_url = %s"
        cursor.execute(select_query, (original_url_str,))
        existing_record = cursor.fetchone()

        if existing_record:
            code = existing_record["short_code"]
            return {
                "short_code": code,
                "short_url": f"{base_url}/{code}",
                "original_url": original_url_str,
            }

        # 2. Generate unique key not present in MySQL
        while True:
            code = generate_short_code()
            check_query = "SELECT id FROM urls WHERE short_code = %s"
            cursor.execute(check_query, (code,))
            if not cursor.fetchone():
                break

        # 3. Save new mapping to MySQL
        insert_query = (
            "INSERT INTO urls (short_code, original_url) VALUES (%s, %s)"
        )
        cursor.execute(insert_query, (code, original_url_str))
        conn.commit()

        return {
            "short_code": code,
            "short_url": f"http://localhost:8000/{code}",
            "original_url": original_url_str,
        }

    finally:
        cursor.close()
        conn.close()


@app.get("/{short_code}")
def redirect_to_url(short_code: str):
    """
    Fetches the original URL from MySQL and redirects the user.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        select_query = (
            "SELECT original_url FROM urls WHERE short_code = %s"
        )
        cursor.execute(select_query, (short_code,))
        record = cursor.fetchone()

        if not record:
            raise HTTPException(status_code=404, detail="Short URL not found")

        return RedirectResponse(url=record["original_url"], status_code=307)

    finally:
        cursor.close()
        conn.close()
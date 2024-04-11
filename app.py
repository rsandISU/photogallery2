import sqlalchemy
from flask import (
    Flask,
    jsonify,
    request,
    make_response,
    render_template,
    redirect,
    session,
)
from google.cloud import storage
from google.cloud.sql.connector import Connector, IPTypes, pymysql
from sqlalchemy import create_engine
import os
import time
import datetime
import exifread
import json
import passwords


from werkzeug.utils import secure_filename

# Flask app configuration
app = Flask(__name__, static_url_path="")
app.secret_key = os.getenv("APP_KEY")

# Google Cloud Platform configuration
GCP_PROJECT_ID = passwords.GCP_PROJECT_ID
GCS_BUCKET_NAME = passwords.GCS_BUCKET_NAME
CLOUD_SQL_CONNECTION_NAME = passwords.CLOUD_SQL_CONNECTION_NAME
CLOUD_SQL_DB_NAME = passwords.CLOUD_SQL_DB_NAME
CLOUD_SQL_USER = passwords.CLOUD_SQL_USER
CLOUD_SQL_PASSWORD = passwords.CLOUD_SQL_PASSWORD

# Cloud Storage client

# Set the environment variable to the path of your service account key
#path = os.path.join("Users", "sandm", "Desktop", "SE_422", "project4-420017-bc05dbc2e8f3.json")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "./project4-420017-bc05dbc2e8f3.json"

storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET_NAME)

# Cloud SQL connection using Google's Cloud SQL Connector
connector = Connector()


connector = Connector()

# function to return the database connection
def getconn():
    conn = connector.connect(
        CLOUD_SQL_CONNECTION_NAME,
        "pymysql",
        user=CLOUD_SQL_USER,
        password=CLOUD_SQL_PASSWORD,
        db=CLOUD_SQL_DB_NAME
    )
    return conn

# create connection pool
pool = sqlalchemy.create_engine(
    "mysql+pymysql://",
    creator=getconn,
)


# SQLAlchemy engine for interacting with the database
#engine = create_engine("postgresql+pg8000://", creator=getconn)
#engine = create_engine('mssql+pytds://', creator=getconn)

# Helper functions
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {
        "png",
        "jpg",
        "jpeg",
    }


def upload_file_to_gcs(file, filename):
    blob = bucket.blob(filename)
    blob.upload_from_file(file)
    return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"


def get_exif_data(file_path):
    with open(file_path, "rb") as file:
        tags = exifread.process_file(file)
    return {
        tag: str(tags[tag])
        for tag in tags
        if tag not in ("JPEGThumbnail", "TIFFThumbnail", "Filename", "EXIF MakerNote")
    }


# Flask routes
@app.route("/", methods=["GET", "POST"])
def upload_photo():
    if request.method == "POST":
        file = request.files["file"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_url = upload_file_to_gcs(file, filename)
            exif_data = get_exif_data(file)
            ts = time.time()
            timestamp = datetime.datetime.fromtimestamp(ts).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            # Insert metadata into Cloud SQL database
            with pool.connect() as conn:
                conn.execute(
                    "INSERT INTO photos (creation_time, title, description, tags, url, exif_data, user_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        timestamp,
                        request.form["title"],
                        request.form["description"],
                        request.form["tags"],
                        file_url,
                        json.dumps(exif_data),
                        session["user"],
                    ),
                )
            return render_template("form.html")
    else:
        return render_template("form.html")


@app.route("/<int:photo_id>", methods=["GET"])
def view_photo(photo_id):
    with pool.connect() as conn:
        result = conn.execute("SELECT * FROM photos WHERE photo_id = %s", (photo_id,))
        photo = result.fetchone()
    return render_template("photodetail.html", photo=photo)


@app.route("/search", methods=["GET"])
def search_page():
    query = request.args.get("query", "")
    with pool.connect() as conn:
        result = conn.execute(
            "SELECT * FROM photos WHERE title LIKE %s OR description LIKE %s OR tags LIKE %s",
            ("%" + query + "%", "%" + query + "%", "%" + query + "%"),
        )
        photos = result.fetchall()
    return render_template("search.html", photos=photos, searchquery=query)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

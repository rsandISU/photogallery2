import MySQLdb
#import sqlalchemy
from flask import Flask, jsonify, request, make_response
from flask import render_template, redirect, session
from google.cloud import storage
#from google.cloud.sql.connector import Connector, IPTypes, pymysql
#from sqlalchemy import create_engine, insert, MetaData
import os
import time
import datetime
import exifread
import json
import passwords


#from werkzeug.utils import secure_filename

# Flask app configuration
app = Flask(__name__, static_url_path="")
app.secret_key = passwords.APP_KEY

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'media')


# Google Cloud Platform configuration
GCP_PROJECT_ID = passwords.GCP_PROJECT_ID
GCS_BUCKET_NAME = passwords.GCS_BUCKET_NAME
CLOUD_SQL_CONNECTION_NAME = passwords.CLOUD_SQL_CONNECTION_NAME
CLOUD_SQL_DB_NAME = passwords.CLOUD_SQL_DB_NAME
CLOUD_SQL_USER = passwords.CLOUD_SQL_USER
CLOUD_SQL_PASSWORD = passwords.CLOUD_SQL_PASSWORD

# Cloud Storage client

# Set the environment variable to the path of your service account key
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "../project4-420017-bc05dbc2e8f3.json"

storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET_NAME)

# Cloud SQL connection using Google's Cloud SQL Connector
#connector = Connector()

db = MySQLdb.connect(host=CLOUD_SQL_CONNECTION_NAME, user=CLOUD_SQL_USER, password=CLOUD_SQL_PASSWORD, db=CLOUD_SQL_DB_NAME)


# function to return the database connection
# def getconn():
#     conn = connector.connect(
#         CLOUD_SQL_CONNECTION_NAME,
#         "pymysql",
#         user=CLOUD_SQL_USER,
#         password=CLOUD_SQL_PASSWORD,
#         db=CLOUD_SQL_DB_NAME
#     )
#     return conn




# db_uri = f"mysql+pymysql://{CLOUD_SQL_USER}:{CLOUD_SQL_PASSWORD}@/{CLOUD_SQL_DB_NAME}?unix_socket=/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"
#
# # Create connection pool
# pool = sqlalchemy.create_engine(
#     db_uri,
#     pool_pre_ping=True,  # Enable automatic connection check
#     pool_recycle=3600,   # Recycle connections after 1 hour
#     creator=getconn,
# )


# create connection pool
# pool = sqlalchemy.create_engine(
#     "mysql+pymysql://",
#     creator=getconn,
# )

# # Create a MetaData object bound to your engine
# metadata = MetaData(bind=pool)
#
# # Reflect the database schema
# metadata.reflect()
#
# # Now you can access the 'users' table
# users_table = metadata.tables['users']



# Helper functions
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {
        "png",
        "jpg",
        "jpeg",
    }


def upload_file_to_gcs(file, filename_with_path, filename):
    blob = bucket.blob(filename)
    blob.upload_from_file(file)
    return f"https://storage.cloud.google.com/{bucket.name}/{filename}?authuser=3"



@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': 'Bad request'}), 400)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


def get_exif_data(path_name):
    f = open(path_name, 'rb')
    tags = exifread.process_file(f)
    exif_data = {}
    for tag in tags.keys():
        if tag not in ('JPEGThumbnail', 'TIFFThumbnail',
                       'Filename', 'EXIF MakerNote'):
            key = "%s" % tag
            val = "%s" % (tags[tag])
            exif_data[key] = val
    return exif_data


@app.route('/', methods=['GET', 'POST'])
def home_page():
    if 'logged_in' in session and session['logged_in']:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM photos WHERE UserID = %s", (session['user'],))
        photos = cursor.fetchall()
        items = []
        for item in photos:
            photo = {}
            photo['PhotoID'] = item[0]
            photo['CreationTime'] = item[1]
            photo['Title'] = item[2]
            photo['Description'] = item[3]
            photo['Tags'] = item[4]
            photo['URL'] = item[5]
            items.append(photo)
        return render_template('index.html', photos=items)
    else:
        return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if 'newusername' in request.form and 'newpassword' in request.form:
            newusername = request.form['newusername']
            newpassword = request.form['newpassword']
            if newusername != "" and newpassword != "":
                cursor = db.cursor()
                cursor.execute("INSERT INTO users (UserID, Password) VALUES (%s, %s)", (newusername, newpassword))
                db.commit()
                session['logged_in'] = True
                session['user'] = newusername
                session['pass'] = newpassword
                return redirect('/')
        if 'username' in request.form and 'password' in request.form:
            username = request.form['username']
            password = request.form['password']
            cursor = db.cursor()
            cursor.execute("SELECT * FROM users WHERE UserID = %s AND Password = %s", (username, password))
            user = cursor.fetchone()
            if user:
                session['logged_in'] = True
                session['user'] = username
                session['pass'] = password
                return redirect('/')
            else:
                return render_template('login.html', error='Invalid username or password')
    return render_template('login.html')

@app.route('/add', methods=['GET', 'POST'])
def add_photo():
    if request.method == 'POST':
        file = request.files['imagefile']
        title = request.form['title']
        tags = request.form['tags']
        description = request.form['description']
        if file and allowed_file(file.filename):
            filename = file.filename
            filename_with_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filename_with_path)
            file.seek(0)
            uploaded_file_url = upload_file_to_gcs(file, filename_with_path, filename)
            exif_data = get_exif_data(filename_with_path)
            ts = time.time()
            timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            cursor = db.cursor()
            cursor.execute("INSERT INTO photos (PhotoID, CreationTime, Title, Description, Tags, URL, EXIF, UserID) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                           (str(int(ts)), timestamp, title, description, tags, uploaded_file_url, json.dumps(exif_data), session["user"]))
            db.commit()
        return redirect('/')
    else:
        return render_template('form.html')

@app.route('/<int:photoID>', methods=['GET'])
def view_photo(photoID):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM photos WHERE PhotoID = %s", (str(photoID),))
    photo = cursor.fetchone()
    if photo:
        tags = photo[4].split(',')
        exif_data = json.loads(photo[6])
        url = photo[5]
        return render_template('photodetail.html', photo=photo, tags=tags, exifdata=exif_data, URL=url)
    else:
        return not_found(None)

@app.route('/search', methods=['GET'])
def search_page():
    query = request.args.get('query', None)
    cursor = db.cursor()
    cursor.execute("SELECT * FROM photos WHERE Title LIKE %s OR Description LIKE %s OR Tags LIKE %s", (f'%{query}%', f'%{query}%', f'%{query}%'))
    photos = cursor.fetchall()
    filtered_items = [item for item in photos if item[7] == session.get('user')]
    items = []
    for item in filtered_items:
        photo = {}
        photo['PhotoID'] = item[0]
        photo['CreationTime'] = item[1]
        photo['Title'] = item[2]
        photo['Description'] = item[3]
        photo['Tags'] = item[4]
        photo['URL'] = item[5]
        items.append(photo)
    return render_template('search.html', photos=items, searchquery=query)



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

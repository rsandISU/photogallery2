"""
MIT License

Copyright (c) 2019 Arshdeep Bahga and Vijay Madisetti

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import boto3
# !flask/bin/python
from flask import Flask, jsonify, request, make_response
from flask import render_template, redirect, session
from passwords import ACCESS_KEY, SECRET_KEY, BUCKET, APP_KEY, INSTANCE_REGION, MONGO_KEY
import os
import time
import datetime
import exifread
import json
from pymongo import MongoClient

# EC2
# app = Flask(__name__, template_folder='/home/ubuntu/photogallery2/Templates', static_url_path="")

app = Flask(__name__, static_url_path="")

app.secret_key = APP_KEY

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'media')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
BASE_URL = "http://localhost:5000/media/"
AWS_ACCESS_KEY = ACCESS_KEY
AWS_SECRET_KEY = SECRET_KEY
REGION = INSTANCE_REGION
BUCKET_NAME = BUCKET

# Connect to MongoDB
MONGODB_CONNECTION_STRING = MONGO_KEY
client = MongoClient(MONGODB_CONNECTION_STRING)
db = client.get_database('project2')
table = db['photos']
users = db['users']


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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


def s3uploading(filename, filename_with_path):
    s3 = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY,
                      aws_secret_access_key=AWS_SECRET_KEY)

    bucket = BUCKET_NAME
    path_filename = "photos/" + filename
    print(path_filename)
    s3.upload_file(filename_with_path, bucket, path_filename)
    s3.put_object_acl(ACL='public-read',
                      Bucket=bucket, Key=path_filename)

    return "https://" + BUCKET_NAME + \
           ".s3.us-east-2.amazonaws.com/" + path_filename


@app.route('/', methods=['GET', 'POST'])
def home_page():
    if 'logged_in' in session and session['logged_in']:
        response = table.find()

        items = list(response)

        filtered_items = [item for item in items if item.get('UserID') == session.get('user')]

        return render_template('index.html', photos=filtered_items)
    else:
        return redirect('/login')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if 'newusername' in request.form and 'newpassword' in request.form:
            newusername = request.form['newusername']
            newpassword = request.form['newpassword']

            if newusername != "" and newpassword != "":
                users.insert_one({
                    "UserID": newusername,
                    "Password": newpassword
                })

                session['logged_in'] = True
                session['user'] = newusername
                session['pass'] = newpassword
                return redirect('/')

        if 'username' in request.form and 'password' in request.form:
            username = request.form['username']
            password = request.form['password']

            user = users.find_one({'UserID': username})
            if user and user.get('Password') == password:
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
            uploaded_file_url = s3uploading(filename, filename_with_path)
            exif_data = get_exif_data(filename_with_path)
            ts = time.time()
            timestamp = datetime.datetime. \
                fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

            table.insert_one({
                "PhotoGalleryKey": str(int(ts * 1000)),
                "CreationTime": timestamp,
                "Title": title,
                "Description": description,
                "Tags": tags,
                "URL": uploaded_file_url,
                "ExifData": json.dumps(exif_data),
                "UserID": session["user"]
            })

        return redirect('/')
    else:
        return render_template('form.html')


@app.route('/<int:photoID>', methods=['GET'])
def view_photo(photoID):
    photo = table.find_one({"PhotoGalleryKey": str(photoID)})
    if photo:
        tags = photo['Tags'].split(',')
        exif_data = json.loads(photo['ExifData'])
        return render_template('photodetail.html', photo=photo, tags=tags, exifdata=exif_data)
    else:
        return not_found(None)


@app.route('/search', methods=['GET'])
def search_page():
    query = request.args.get('query', None)

    items = table.find({
        "$or": [
            {"Title": {"$regex": query, "$options": "i"}},
            {"Description": {"$regex": query, "$options": "i"}},
            {"Tags": {"$regex": query, "$options": "i"}}
        ]
    })

    filtered_items = [item for item in items if item.get('UserID') == session.get('user')]

    return render_template('search.html', photos=filtered_items, searchquery=query)


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)

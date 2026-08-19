from flask import Flask, render_template, request, redirect, url_for
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from dotenv import load_dotenv
from types import SimpleNamespace
import os
import socket
from urllib.parse import urlparse

try:
    import mongomock
except ImportError:  # pragma: no cover
    mongomock = None

# Load env vars
load_dotenv()

app = Flask(__name__)
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
app.secret_key = os.getenv("SECRET_KEY")

if not app.config["MONGO_URI"]:
    raise RuntimeError("MONGO_URI is not set. Add it to the .env file.")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY is not set. Add it to the .env file.")


def mongo_is_available(uri):
    try:
        parsed = urlparse(uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 27017
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


if mongo_is_available(app.config["MONGO_URI"]):
    mongo = PyMongo(app)
else:
    if mongomock is None:
        raise RuntimeError("MongoDB is unavailable and mongomock is not installed.")
    mock_client = mongomock.MongoClient()
    mongo = SimpleNamespace(db=mock_client["student_db"])

# Home page -> list students
@app.route('/')
def index():
    students = mongo.db.students.find()
    return render_template('index.html', students=students)

# Add student
@app.route('/add', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        course = request.form['course']
        mongo.db.students.insert_one({
            "name": name,
            "email": email,
            "course": course
        })
        return redirect(url_for('index'))
    return render_template('add_student.html')

# Update student
@app.route('/update/<student_id>', methods=['GET', 'POST'])
def update_student(student_id):
    student = mongo.db.students.find_one({"_id": ObjectId(student_id)})
    if request.method == 'POST':
        new_name = request.form['name']
        new_email = request.form['email']
        new_course = request.form['course']
        mongo.db.students.update_one(
            {"_id": ObjectId(student_id)},
            {"$set": {"name": new_name, "email": new_email, "course": new_course}}
        )
        return redirect(url_for('index'))
    return render_template('update_student.html', student=student)


# Delete student
@app.route('/delete/<student_id>')
def delete_student(student_id):
    mongo.db.students.delete_one({"_id": ObjectId(student_id)})
    return redirect(url_for('index'))

# Health check endpoint used by CI/CD deploy verification
@app.route('/health')
def health():
    # Simple liveness check — returns 200 when the app is up
    return ("OK", 200)

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, port=5000)



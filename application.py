import os
import psycopg2
import json
import requests

from flask import Flask, session, render_template, request,  redirect, url_for, jsonify, flash
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from datetime import timedelta

app = Flask(__name__)
app.secret_key = os.getenv("KEY")
# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

#api goodreads KEY
key = "j5aiHcNz7TNxFnU6mEkw7Q"

@app.route("/")
def index():
        return render_template('index.html')

@app.route("/register", methods=["POST", "GET"])
def register():
    # get user input from the html form
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirm")

        check_user = db.execute("SELECT * FROM users WHERE username = :username and password = :password", {'username' : username, 'password' :password}).fetchall()
        if check_user:
           flash('You are already registered.', 'info')
           return redirect(url_for('index'))
        else :
            db.execute("INSERT INTO users (username, password) VALUES (:username, :password)",
                    {"username": username, "password": password})
            db.commit()
            #save the data in session
            session['username'] = username
            session['password'] = password
            return render_template('success.html')

        if 'username' in session:
            flash('Already Signed In.')
            return redirect(url_for('search'))
        else:
            return render_template('index.html')

@app.route('/signin_validation', methods=["POST", "GET"])
def signin_validation():
    if request.method == 'POST':
        # get user info from input
        username = request.form.get("username")
        password = request.form.get("password")
        # check if password match with database
        check_user = db.execute("SELECT * FROM users WHERE username = :username and password= :password",
                         {'username': username, 'password': password}).fetchall()
        if check_user:
            session["user_id"]= check_user[0][0]
            session["username"]= check_user[0][1]
            session["date"]= check_user[0][3]
            flash('Sign in Successful', 'success')
            return render_template("search.html")
        else:
            flash('Username or Password is Incorrect', 'danger')
            return redirect(url_for('index'))

@app.route('/sign_out')
def sign_out():
    session.pop('username')
    return redirect(url_for('index'))

@app.route('/account')
def account():

    if 'user_id' in session:
        user_id = session['user_id']
        user_query = db.execute("SELECT * FROM users WHERE id = :id",
                        {'id': user_id}).fetchall()
        review_query = db.execute("SELECT * FROM reviews WHERE user_id = :user_id", {"user_id": user_id}).fetchall()
       # root = request.url_root()
        userInfo = {
            'username': session['username'],
            'user_id': session['user_id'],
            'password': user_query[0][2],
            'date': user_query[0][3]
        }
        reviewCount = len(review_query)
        return render_template('account.html', userInfo = userInfo, reviewedbooks = review_query , reviewCount= reviewCount)

@app.route('/search', methods=["GET", "POST"])
def search():
    if request.method == "GET":
        return render_template("search.html")
    if request.method == "POST":
        search = request.form.get("search")
        search = '%' + search + '%'
        books = db.execute("SELECT * FROM books WHERE LOWER(title) LIKE LOWER(:search) OR LOWER(author) LIKE LOWER(:search) OR isbn LIKE :search OR year LIKE :search", {"search": search}).fetchall()
        return render_template("booklist.html", books=books)

@app.route('/book/<book_id>', methods=['GET', 'POST'])
def book_view(book_id):

    if request.method == "GET":
        book = db.execute("SELECT * FROM books WHERE id=:id", {"id": book_id}).fetchone()
        #Get API data from GoodReads
        try:
            goodreads = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": key, "isbns": book.isbn})
        except Exception as e:
            return render_template("error.html", message = e)

        # Get comments particular to one book
        reviews = db.execute("SELECT username, comment, rating FROM users JOIN reviews ON reviews.user_id=users.id WHERE book_id = :book_id", {"book_id": book_id}).fetchall()
        if not book:
            return render_template("error.html", message="Invalid book id")

        return render_template("book.html", book=book, reviews=reviews, book_id=book_id, goodreads=goodreads.json()["books"][0])
    else:
        ######## Check if the user commented on this particular book before ###########
        review_status = db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id", {
                                  "user_id": session["user_id"], "book_id": book_id}).fetchone()
        if review_status:
            return render_template("error.html", message = "You reviewed this book before!")

        ######## Proceed to get user comment ###########
        comment = request.form.get("comment")
        rating = request.form.get("rating")

        if not comment:
            return render_template("error.html", message="Please Rate and Review book.")
        try:
            # Insert into reviews table
            db.execute("INSERT INTO reviews (user_id, book_id, rating, comment) VALUES (:user_id, :book_id, :rating, :comment)", {
                        "user_id": session["user_id"], "book_id": book_id, "rating": rating, "comment": comment})
        except Exception as e:
            return render_template("error.html", message=e)
        db.commit()
        return redirect(url_for("book_view", book_id=book_id))

@app.route('/api/<isbn>')
def api(isbn):
    # get information from database.
    result = db.execute(
        "SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()

    # Error-check.
    if result is None:
        return jsonify({
            "message": "error - Book not in database."
        })

    # get information from Goodreads API
    res = requests.get("https://www.goodreads.com/book/review_counts.json",
                       params={"key": "j5aiHcNz7TNxFnU6mEkw7Q", "isbns": isbn})
    data = res.json()
    average_rating = data["books"][0]["average_rating"]
    work_ratings_count = data["books"][0]["work_ratings_count"]

    # Return jsonify'd information.
    return jsonify({
        "title": result.title,
        "author": result.author,
        "year": result.year,
        "isbn": result.isbn,
        "review_count": work_ratings_count,
        "average_score": average_rating
    })
@app.errorhandler(404)
def page_not_found(e):

    return render_template('404page.html'), 404

if __name__ == "__main__":
    app.secret_key = 'hello'
    app.run()

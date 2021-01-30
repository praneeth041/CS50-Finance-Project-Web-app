import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

#functions to check invalid inputs
def is_provided(field):
    if not request.form.get(field):
        return apology(f"must provide {field}", 403)

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    rows = db.execute("""
            SELECT symbol,
                SUM(shares) as totalShares
            FROM History
                WHERE user_id = :user_id
                GROUP BY symbol
                HAVING totalShares > 0
                """,
                user_id = session["user_id"])

    portfolio_table = []
    total_cash = 0

    for row in rows:

        stock = lookup(row["symbol"])

        portfolio_table.append({
            "Symbol": stock["symbol"],
            "Name" : stock["name"],
            "Shares" : row["totalShares"],
            "Price" : usd(stock["price"]),
            "Total" : usd(stock["price"] * row["totalShares"])
        })
        total_cash += stock['price'] * row["totalShares"]

    rows = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
    cash_left = rows[0]["cash"]

    total_cash += cash_left

    return render_template("index.html", portfolioTable = portfolio_table, cash = usd(cash_left), total_cash = usd(total_cash))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        result_check = is_provided("symbol") or is_provided("shares")
        if result_check is not None:
            return apology("Please provide a Symbol and/or no.of shares you want to buy", 400)

        if lookup(request.form.get("symbol").upper()) is None:
            return apology("Invalid Symbol", 400)

        if not request.form.get("shares").isdigit():
            return apology("Invalid number of shares", 400)

        stock = lookup(request.form.get("symbol").upper())
        stock_price = stock['price']
        number_of_shares = int(request.form.get("shares"))

        rows = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
        current_cash = rows[0]["cash"]

        updated_cash = current_cash - stock_price * number_of_shares

        if current_cash < stock_price:
            return apology("Can't Afford", 400)

        db.execute("UPDATE users SET cash = :updated_cash WHERE id = :id",
                        updated_cash = updated_cash, id = session["user_id"])

        db.execute("""
            INSERT INTO History
                (user_id, symbol, shares, price)
            VALUES (:user_id, :symbol, :shares, :price)
            """,
                user_id = session["user_id"],
                symbol = stock['symbol'],
                shares = number_of_shares,
                price = stock_price
                )

        flash("Bought!")
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows = db.execute("""
            SELECT symbol, shares, price, time AS Transacted
            FROM History
                WHERE user_id = :user_id
                GROUP BY Transacted
                """,
                user_id = session["user_id"])

    history = []

    for row in rows:

        history.append({
            "Symbol": row["symbol"],
            "Shares" : row["shares"],
            "Price" : row["price"],
            "Transacted" : row["Transacted"]
        })

    return render_template("history.html", history = history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        # Ensure password was submitted
        result = is_provided("username") or is_provided("password")
        if result is not None:
            return result

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":

        result_check = is_provided("symbol")
        if result_check is not None:
            return result_check

        Symbol = request.form.get("symbol").upper()
        check = lookup(Symbol)

        if check is None:
            return apology("Invalid Symbol", 400)
        else:
            return render_template("quoted.html", stock={
                'name': check['name'],
                'price': usd(check['price']),
                'symbol': check['symbol']
            })

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        result_checks = is_provided("username") or is_provided("password") or is_provided("confirmation")

        if result_checks is not None:
            return result_checks
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Both passwords must be same")

        try:
            values = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                    username = request.form.get("username"), hash = generate_password_hash((request.form.get("password"))))
        except:
            return apology("Username already exists, try a different username", 403)

        if values is None:
            return apology("Registration Error", 403)

        session["user_id"] = values
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        missing_errors = is_provided("symbol") or is_provided("shares")
        if missing_errors is not None:
            return apology("Please provide a Symbol and/or no.of shares you want to sell", 400)

        if not request.form.get("shares").isdigit():
            return apology("Invalid number of shares", 400)

        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))
        stock = lookup(symbol)

        if stock is None:
            return apology("Invalid Symbol!")

        rows = db.execute("""
                            SELECT symbol, SUM(shares) AS Shares FROM History
                            WHERE user_id = :user_id
                            GROUP BY symbol
                            HAVING Shares > 0
                          """,
                            user_id = session["user_id"],
                         )

        for row in rows:
            if row["symbol"] == symbol:
                if shares > row["Shares"]:
                    return apology("Too Many Shares!!")

        rows = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
        current_cash = rows[0]["cash"]

        updated_cash = current_cash + shares * stock["price"]

        db.execute("UPDATE users SET cash = :updated_cash WHERE id = :id",
                    updated_cash = updated_cash, id = session["user_id"])

        db.execute("""
            INSERT INTO History
                (user_id, symbol, shares, price)
            VALUES (:user_id, :symbol, :shares, :price)
            """,
                user_id = session["user_id"],
                symbol = stock['symbol'],
                shares = -1 * shares,
                price = stock["price"]
                )

        flash("Sold!")
        return redirect("/")

    else:

        rows = db.execute("""
                SELECT symbol
                FROM History
                WHERE user_id = :user_id
                GROUP BY symbol
                HAVING SUM(shares) > 0
                """,
                user_id = session["user_id"])

        return render_template("sell.html", symbols = [row["symbol"] for row in rows])

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

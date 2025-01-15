from flask import Flask, render_template, redirect, url_for, request
from forms import PreTripForm, PostTripForm  # import from forms.py

app = Flask(__name__)
app.config["SECRET_KEY"] = "CHANGE_THIS_TO_SOMETHING_SECURE"

@app.route("/")
def index():
    return "<h1>Welcome! Go to /new_pretrip</h1>"

@app.route("/new_pretrip", methods=["GET", "POST"])
def new_pretrip():
    form = PreTripForm()
    if form.validate_on_submit():
        # Here you’d normally save to DB, etc.
        # For demonstration, we'll just print to console and redirect.
        print("Truck number:", form.truck_number.data)
        print("Shift:", form.shift.data)
        return redirect(url_for("index"))

    return render_template("new_pretrip.html", form=form)

@app.route("/posttrip/<int:id>", methods=["GET", "POST"])
def complete_posttrip(id):
    form = PostTripForm()
    if form.validate_on_submit():
        # Example: save posttrip data
        print("Ending mileage:", form.end_mileage.data)
        print("Remarks:", form.remarks.data)
        return redirect(url_for("index"))

    return render_template("complete_posttrip.html", form=form, pretrip_id=id)

if __name__ == "__main__":
    app.run(debug=True)

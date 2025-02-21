"""
forms.py - All WTForms for your LacksDrivers application.
"""
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    TextAreaField,
    BooleanField,
    SelectField,
    SubmitField
)
from wtforms.validators import DataRequired

############################################################################
# 1) TASK FORMS
############################################################################
class TaskForm(FlaskForm):
    """
    Form for creating a new Task.
    """
    title = StringField("Title", validators=[DataRequired()])
    details = TextAreaField("Details")
    is_hot = BooleanField("Mark as HOT")
    shift = SelectField("Shift", choices=[("1st","1st"),("2nd","2nd"),("3rd","3rd")])
    assigned_to = SelectField("Assign To (Driver)", coerce=int)
    submit = SubmitField("Create Task")


class UpdateTaskForm(FlaskForm):
    """
    Form for updating an existing Task.
    """
    title = StringField("Title", validators=[DataRequired()])
    details = TextAreaField("Details")
    is_hot = BooleanField("Hot Task?")
    shift = SelectField("Shift", choices=[("1st","1st"),("2nd","2nd"),("3rd","3rd")])
    # Add more fields if you need them (e.g. status, assigned_to, etc.)
    # Then a SubmitField if you want a dedicated submit button.


############################################################################
# 2) ANNOUNCEMENT FORM
############################################################################
class AnnouncementForm(FlaskForm):
    """
    Form for creating a new Announcement.
    """
    title = StringField("Announcement Title", validators=[DataRequired()])
    body = TextAreaField("Announcement Body", validators=[DataRequired()])
    submit = SubmitField("Post Announcement")


############################################################################
# 3) DRIVER LOG FORM
############################################################################
class DriverLogForm(FlaskForm):
    maintenance = BooleanField("Maintenance")
    fuel = BooleanField("Fuel")
    meeting = BooleanField("Meeting")

    plant_name = SelectField(
        "Plant Name",
        choices=[
            ("", "Select Plant..."),
            ("RE","RE"),
            ("RW","RW"),
            ("PC","PC"),
            ("PE","PE"),
            ("PW","PW"),
            ("KP","KP"),
            ("PPL","PPL"),
            ("DC","DC"),
            ("Helios","Helios"),
            ("BP","BP"),
            ("52L","52L"),
            ("Trim DC","Trim DC"),
            ("52DC","52DC"),
            ("ALN","ALN"),
            ("AWE","AWE"),
            ("CORP","CORP"),
            ("R&D","R&D"),
            ("GLA","GLA"),
            ("KM","KM"),
            ("KS","KS"),
            ("MONROE","MONROE"),
            ("Other","Other"),
            ("Lab","Lab")
        ],
        validators=[DataRequired()]
    )
    load_size = SelectField(
        "Load Size",
        choices=[
            ("", "Select Load Size..."),
            ("Empty","Empty"),
            ("Quarter","Quarter"),
            ("Half","Half"),
            ("Partial","Partial"),
            ("Full","Full"),
            ("Hazmat","Hazmat")
        ],
        validators=[DataRequired()]
    )
    downtime_reason = StringField("Downtime Reason (optional)")
    
    # Field for manual depart time in HH:MM format.
    depart_time = StringField(
        "Depart Time (optional)",
        description="Enter time like '545' for 05:45 or '13:05' for 13:05"
    )

    submit = SubmitField("Submit Log Entry")

############################################################################
# 4) PRE-TRIP & POST-TRIP FORMS
############################################################################
class PreTripForm(FlaskForm):
    """
    Form for creating/editing a PreTrip record.
    """
    # Basic info
    truck_number = StringField("Truck / Tractor #", validators=[DataRequired()])
    trailer_number = StringField("Trailer #")
    pretrip_date = StringField("PreTrip Date")
    shift = SelectField("Shift", choices=[("1st","1st"), ("2nd","2nd"), ("3rd","3rd")])
    start_mileage = StringField("Start Mileage")

    # Additional
    truck_type = SelectField(
        "Truck Type",
        choices=[("Tractor", "Tractor"), ("Pickup", "Pickup"), ("Other", "Other")]
    )
    oil_system_status = SelectField(
        "Oil System Status",
        choices=[("good", "Good"), ("low", "Low"), ("leaking", "Leaking")]
    )
    tires_ok = BooleanField("Tires OK")
    tires_status = SelectField(
        "Tires Status",
        choices=[("good", "Good"), ("needs_replacement", "Needs Replacement")]
    )

    # GENERAL CONDITION
    cab_doors_windows = BooleanField("Cab Doors/Windows")
    body_doors = BooleanField("Body Doors")
    oil_leak = BooleanField("Oil Leak")
    grease_leak = BooleanField("Grease Leak")
    coolant_leak = BooleanField("Coolant Leak")
    fuel_leak = BooleanField("Fuel Leak")
    gc_no_defects = BooleanField("No Defects (General Condition)")

    # IN-CAB
    gauges_warning = BooleanField("Gauges/Warning Indicators")
    wipers = BooleanField("Windshield Wipers/Washers")
    horn = BooleanField("Horn")
    heater_defroster = BooleanField("Heater/Defroster")
    mirrors = BooleanField("Mirrors")
    seat_belts_steering = BooleanField("Seat Belts/Steering")
    clutch = BooleanField("Clutch")
    service_brakes = BooleanField("Service Brakes")
    parking_brake = BooleanField("Parking Brake")
    emergency_brakes = BooleanField("Emergency Brakes")
    triangles = BooleanField("Triangles")
    fire_extinguisher = BooleanField("Fire Extinguisher")
    safety_equipment = BooleanField("Safety Equipment")
    incab_no_defects = BooleanField("No Defects (In-Cab)")

    # ENGINE COMPARTMENT
    oil_level = BooleanField("Oil Level")
    coolant_level = BooleanField("Coolant Level")
    belts = BooleanField("Belts")
    hoses = BooleanField("Hoses")
    ec_no_defects = BooleanField("No Defects (Engine Compartment)")

    # EXTERIOR
    lights_working = BooleanField("Lights Working")
    reflectors = BooleanField("Reflectors")
    suspension = BooleanField("Suspension")
    tires = BooleanField("Tires")
    wheels_rims = BooleanField("Wheels/Rims")
    battery = BooleanField("Battery")
    exhaust = BooleanField("Exhaust")
    brakes = BooleanField("Brakes")
    air_lines = BooleanField("Air Lines")
    light_line = BooleanField("Light Line")
    fifth_wheel = BooleanField("Fifth Wheel")
    coupling = BooleanField("Coupling")
    tie_downs = BooleanField("Tie Downs")
    rear_end_protection = BooleanField("Rear End Protection")
    exterior_no_defects = BooleanField("No Defects (Exterior)")

    # TOWED UNIT
    towed_bodydoors = BooleanField("Body/Doors")
    towed_tiedowns = BooleanField("Tie-Downs")
    towed_lights = BooleanField("Lights")
    towed_reflectors = BooleanField("Reflectors")
    towed_suspension = BooleanField("Suspension")
    towed_tires = BooleanField("Tires")
    towed_wheels = BooleanField("Wheels")
    towed_brakes = BooleanField("Brakes")
    towed_landing_gear = BooleanField("Landing Gear")
    towed_kingpin = BooleanField("Kingpin")
    towed_fifthwheel = BooleanField("Fifth Wheel")
    towed_othercoupling = BooleanField("Other Coupling")
    towed_rearend = BooleanField("Rear End")
    towed_no_defects = BooleanField("No Defects (Towed Unit)")

    # REMARKS / DAMAGE
    damage_report = TextAreaField("Damage Report")

    # SUBMIT
    submit = SubmitField("Save PreTrip")


class PostTripForm(FlaskForm):
    """
    Form for creating/editing a PostTrip record.
    """
    end_mileage = StringField("Ending Mileage")
    remarks = TextAreaField("Remarks")
    submit = SubmitField("Complete PostTrip")

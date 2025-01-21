from flask_wtf import FlaskForm
from wtforms import (
    StringField, 
    TextAreaField, 
    BooleanField, 
    SelectField, 
    SubmitField
)
from wtforms.validators import DataRequired

#
# Example other forms
#
class TaskForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    details = TextAreaField("Details")
    is_hot = BooleanField("Mark as HOT")
    shift = SelectField("Shift", choices=[("1st","1st"),("2nd","2nd"),("3rd","3rd")])
    assigned_to = SelectField("Assign To (Driver)", coerce=int)
    submit = SubmitField("Create Task")


class UpdateTaskForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    details = TextAreaField("Details")
    is_hot = BooleanField("Hot Task?")
    shift = SelectField("Shift", choices=[("1st","1st"),("2nd","2nd"),("3rd","3rd")])
    # Add other fields/submit if needed


class AnnouncementForm(FlaskForm):
    title = StringField("Announcement Title", validators=[DataRequired()])
    body = TextAreaField("Announcement Body", validators=[DataRequired()])


#
# PRE-TRIP FORM
#
class PreTripForm(FlaskForm):
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
    tires_ok = BooleanField("Tires OK")  # <-- ensures `tires_ok` is defined
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


#
# POST-TRIP FORM
#
class PostTripForm(FlaskForm):
    end_mileage = StringField("Ending Mileage")
    remarks = TextAreaField("Remarks")
    submit = SubmitField("Complete PostTrip")
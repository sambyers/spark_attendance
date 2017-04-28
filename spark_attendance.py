from flask import Flask, request
from ciscosparkapi import CiscoSparkAPI
import re
import os
from flask_sqlalchemy import SQLAlchemy
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db = SQLAlchemy(app)

os.environ['SPARK_ACCESS_TOKEN'] = 'YOUR SPARK ACCESS TOKEN'

spark_api = CiscoSparkAPI()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=False)
    room_id = db.Column(db.String(120), unique=False)

    def __init__(self, email, room_id):
        self.email = email
        self.room_id = room_id

    def __repr__(self):
        return '<User %r>' % self.email

def get_checkedin_users(room_id=None, return_format=None):
    '''
    room_id is the Spark room ID
    format is the return format needed, either str, list, or csv
    '''

    users_in_room = User.query.filter_by(room_id=room_id).all()

    if return_format is 'str':
        users_in_room_str = "\n".join(str(x.email) for x in users_in_room)
        return users_in_room_str

    if return_format is 'list':
        users_in_room_lst = [user.email for user in users_in_room]
        return users_in_room_lst

    if return_format is 'csv':
        users_in_room_str = "Display Name, Email"
        email_addresses = [user.email for user in users_in_room]
        for email in email_addresses:
            display_name = get_display_name(email)
            users_in_room_str += "\n"+display_name + ", " +email
        return users_in_room_str

def get_display_name(person_email=None):
    people = spark_api.people.list(email=person_email, max=1)
    for person in people:
        display_name = person.displayName
    return display_name

@app.route("/", methods=['POST'])
def index():
    if request.method == "POST":
        # We have to force true here because Spark isn't sending us Content-Type: application/json
        data = request.get_json(force=True)

    if data["appId"] == 'YOUR APP ID FROM SPARK -YOU COULD ALSO PUT THIS SOMEWHERE MORE SENSIBLE LIKE AN ENVIRONMENTAL VAR':
        if data:
            msg_id = data["data"]["id"]
            room_id = data["data"]["roomId"]
            person_email = data["data"]["personEmail"]
            
        if msg_id:
            spark_msg = spark_api.messages.get(msg_id)

        if 'here' in spark_msg.text:
            already_in_db = User.query.filter_by(email=person_email,room_id=room_id).all()

            if not already_in_db:
                display_name = get_display_name(person_email)
                user = User(person_email, room_id)
                db.session.add(user)
                db.session.commit()
                spark_api.messages.create(roomId=room_id, text=display_name+" has been checked in.")

        elif 'help' in spark_msg.text:
                spark_api.messages.create(roomId=room_id, text="You can use Spark Attendance with the following commands:\n    \"here\" to check in.\n    \"list\" to list the users that have checked in.\n \"export\" will attach a csv file to the room with the users currently checked in.\n \"clear\" will clear out the users checked in.")

        elif 'list all' in spark_msg.text:
            if person_email == 'someone@somedomain.com': # restricting commands to just a particular person
                users_in_room = User.query.all()
                users_in_room_str = "\n".join(str(x.email) for x in users_in_room)
                if users_in_room_str:
                    spark_api.messages.create(roomId=room_id, text=users_in_room_str)
                else:
                    spark_api.messages.create(roomId=room_id, text="There are no users checked in.")

        elif 'list' in spark_msg.text:
            users_in_room_str = get_checkedin_users(room_id=room_id, return_format='str')
            if users_in_room_str:
                spark_api.messages.create(roomId=room_id, text="Users that have checked in:\n"+users_in_room_str)
            else:
                spark_api.messages.create(roomId=room_id, text="There are no users checked in for this room.")

        elif 'clear' in spark_msg.text:
            room_membership = spark_api.memberships.list(roomId=room_id, personEmail=person_email, max=1)
            # There's only even 1 item in this iterator, given we're filtering for person and room (there can only be 1 instance of a person in a room)
            for item in room_membership:
                mod = item.isModerator

            if mod is False:
                spark_api.messages.create(roomId=room_id, text="Only a room moderator can clear checked-in users.")

            if mod is True:
                users_in_room = User.query.filter_by(room_id=room_id).all()

                for user in users_in_room:
                    db.session.delete(user)
                db.session.commit()
                spark_api.messages.create(roomId=room_id, text="All users that were checked in have been cleared.")
        elif 'export' in spark_msg.text:
            users_csv = get_checkedin_users(room_id=room_id, return_format='csv')
            with open('export.csv', 'w') as myfile:     
                myfile.write(users_csv)
            files = ['export.csv']
            spark_api.messages.create(roomId=room_id, text="Export of checked-in users attached to room.", files=files)
            os.remove('export.csv')

        return "200 OK"
    return "400 Bad Request"

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0')

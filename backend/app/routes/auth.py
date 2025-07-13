from flask import Flask, redirect, request, jsonify, session
import requests
from dotenv import load_dotenv
import os
import urllib.parse
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = "94ac6d79efad4980616c2f988b4f720a5c936dc874d6a0868499f45e7a7a9c84"

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
API_BASE_URL = 'https://api.spotify.com/v1/'

# pylint: disable=E1101
@app.route('/')
def index():
    return "welcome to my spotify app <a href='/login'>Log in with spotify</a>"

@app.route('/login')
def login():
    scope = 'user-read-private user-read-email'

    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'scope': scope,
        'redirect_uri': REDIRECT_URI,
        'show_dialog': True
    }

    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    return redirect(auth_url)


@app.route('/callback')
def callback():
    if 'error' in request.args:
        return jsonify({"error": request.args['error']})
    
    if 'code' in request.args: 
        req_body = {
            'code' : request.args['code'],
            'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT_URI,
            'client_id': CLIENT_ID, 
            'client_secret': CLIENT_SECRET
        }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(TOKEN_URL, data = req_body, headers=headers)
    if response.status_code != 200:
        return jsonify(response.json()), 400     

    token_info = response.json()
    
    session['access_token'] = token_info['access_token']
    session['refresh_token'] = token_info['refresh_token']
    session['expires_at'] = datetime.now().timestamp() + 10

    return redirect('/refresh-token')


@app.route('/refresh-token')
def refresh_token():
    if 'refresh_token' not in session:
        return redirect('/login')
    if datetime.now().timestamp() > session['expires_at']:
        print("TOKEN EXPIRED REFRESHING...")

        req_body = {
            'grant_type': 'refresh_token',
            'refresh_token': session['refresh_token'],
            'client_id': CLIENT_ID, 
            'client_secret': CLIENT_SECRET
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        print(req_body)
        response = requests.post(TOKEN_URL, data = req_body, headers=headers)
        print(response.status_code, response.text)  
        new_token_info = response.json()

        print(response.status_code)
        print(response.text)

        session['access_token'] = new_token_info['access_token']
        session['expires_at'] = datetime.now().timestamp() + 10

        return "refreshed"
    
    return "still valid"
    
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug = True)


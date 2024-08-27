import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fasthtml.common import *
from fasthtml.oauth import GoogleAppClient


# # Set up a database
db = database('data/user_counts.db')
user_counts = db.t.user_counts
if user_counts not in db.t:
    user_counts.create(dict(name=str, count=int, signed_up=bool), pk='name', transform=True)
Count = user_counts.dataclass()

# Auth client setup for GitHub
client = GoogleAppClient(os.getenv("AUTH_CLIENT_ID"), 
                         os.getenv("AUTH_CLIENT_SECRET"),
                         redirect_uri="http://localhost:8000/auth_redirect")
login_link = client.login_link()


# Beforeware that puts the user_id in the request scope or redirects to the login page if not logged in.
def before(req, session):
    auth = req.scope['auth'] = session.get('user_id', None)
    if not auth:
        return RedirectResponse('/login', status_code=303)
    if auth not in user_counts:
        return RedirectResponse('/login', status_code=303)
    user = user_counts[auth]
    if not user.signed_up and req.url.path != '/signup':
        return RedirectResponse('/signup', status_code=303)

bware = Beforeware(before, skip=['/login', '/auth_redirect'])

app = FastHTML(before=bware)

# Homepage (only visible if logged in)
@app.get('/')
def home(auth):
    user = user_counts[auth]
    return Div(
        P(f"Hello, {user.name}"),
        P(A('Logout', href='/logout'))
    )

@app.get('/increment')
def increment(auth):
    c = user_counts[auth]
    c.count += 1
    return user_counts.upsert(c).count

# The login page has a link to the GitHub login page.
@app.get('/login')
def login(): 
    return Div(P("You are not logged in."), 
               A('Log in with Google', href=client.login_link()))

# To log out, we just remove the user_id from the session.
@app.get('/logout')
def logout(session):
    session.pop('user_id', None)
    return RedirectResponse('/login', status_code=303)

# The redirect page is where the user is sent after logging in.
@app.get('/auth_redirect')
def auth_redirect(code:str, session, state:str=None):
    if not code: return "No code provided!"
    print(f"code: {code}")
    print(f"state: {state}") # Not used in this example.
    try:
        # The code can be used once, to get the user info:
        info = client.retr_info(code)
        print(f"info: {info}")
        # Use client.retr_id(code) directly if you just want the id, otherwise get the id with:
        user_id = info[client.id_key]
        print(f"User id: {user_id}")
        # Access token (populated after retr_info or retr_id) - unique to this user,
        # and sometimes used to revoke the login. Not used in this case.
        token = client.token["access_token"]
        print(f"access_token: {token}")

        # We put the user_id in the session, so we can use it later.
        session['user_id'] = user_id

        # We also add the user in the database, if they are not already there.
        if user_id not in user_counts:
            user_counts.insert(name=user_id, count=0, signed_up=False)

        # Redirect to the homepage
        return RedirectResponse('/', status_code=303)

    except Exception as e:
        print(f"Error: {e}")
        return f"Could not log in."

serve(port=8000)

@app.get('/signup')
def signup(auth):
    return Div(
        P("Please complete your signup"),
        Form(
            Input(name="name", placeholder="Your name"),
            Button("Sign up", type="submit"),
            method="POST",
            action="/signup"
        )
    )

@app.post('/signup')
def process_signup(auth, name: str, session):
    print(f"auth: {auth}")
    print(f"session: {session}")
    
    if auth not in user_counts:
        session.pop('user_id', None)
        return RedirectResponse('/login', status_code=303)

    user = user_counts[auth]
    user.name = name
    user.signed_up = True
    user_counts.upsert(user)
    return RedirectResponse('/', status_code=303)
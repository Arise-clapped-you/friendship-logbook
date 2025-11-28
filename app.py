from flask import Flask, render_template, redirect, url_for, request
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
# In app.py, add to your imports:
from werkzeug.utils import secure_filename 

# --- 0. ENV LOADING ---
load_dotenv() 

# --- 1. APP CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY') 
DB_NAME = 'logbook.db'

# --- 2. LOGIN MANAGER SETUP ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- New Configuration (near APP CONFIGURATION) ---
UPLOAD_FOLDER = 'static/uploads' # Directory where images will be saved
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Helper function to check file extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- DATABASE FUNCTIONS ---

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    conn = get_db_connection()
    
    # 1. Create the MEMORY table (for map pins)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            story TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            photo_url TEXT,
            date DATE NOT NULL,
            user_id INTEGER NOT NULL
        )
    ''')
    
    # 2. Create the APPRECIATION table (for the lists)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS appreciation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            author_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL
        )
    ''')
    
    # 3. Create the USER table 
    conn.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Insert initial users if the table is empty
    cursor = conn.execute("SELECT COUNT(*) FROM user")
    if cursor.fetchone()[0] == 0:
        your_pwd_hash = generate_password_hash(os.getenv('YOUR_PASSWORD'))
        friend_pwd_hash = generate_password_hash(os.getenv('FRIEND_PASSWORD'))

        conn.execute("INSERT INTO user (id, username, password_hash) VALUES (?, ?, ?)", 
                     (1, 'You', your_pwd_hash))
        conn.execute("INSERT INTO user (id, username, password_hash) VALUES (?, ?, ?)", 
                     (2, 'Friend', friend_pwd_hash))
        
    conn.commit()
    conn.close()

# Run the database initialization when the app starts
init_db()


# --- 3. USER MODEL ---
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username
        
@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user_row = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user_row:
        return User(user_row['id'], user_row['username']) 
    return None

# --- 4. ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user_row = conn.execute("SELECT * FROM user WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user_row and check_password_hash(user_row['password_hash'], password):
            user = load_user(user_row['id']) 
            login_user(user)
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error='Invalid credentials')
            
    return render_template('login.html', error=None)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    conn = get_db_connection()
    
    # 1. Fetch the raw memory data (list of Row objects)
    memories_rows = conn.execute('SELECT * FROM memory ORDER BY date DESC').fetchall()
    conn.close()
    
    # 2. CONVERSION STEP (FIX for JSON serialization error): 
    # Convert Row objects to serializable dictionaries
    memories = []
    for row in memories_rows:
        memories.append(dict(row)) 
    
    return render_template(
        'index.html', 
        username=current_user.username or 'Guest',
        memories=memories # This list is now safe for `tojson`
    )

@app.route('/add_memory', methods=['GET', 'POST'])
@login_required
def add_memory():
    if request.method == 'POST':
        title = request.form['title']
        story = request.form['story']
        latitude = request.form['latitude']
        longitude = request.form['longitude']
        date = request.form['date']
        
        photo_url = None # Default value

        # --- FILE UPLOAD LOGIC ---
        if 'photo' in request.files:
            file = request.files['photo']
            
            # If the user selected a file and it has an allowed extension
            if file and allowed_file(file.filename):
                # Secure the filename to prevent directory traversal attacks
                filename = secure_filename(file.filename)
                
                # Create the full file path
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Ensure the uploads directory exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                # Save the file to the local directory
                file.save(filepath)
                
                # The photo_url stored in the database is the relative path (static/uploads/filename.jpg)
                photo_url = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        # --- END FILE UPLOAD LOGIC ---

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO memory (title, story, latitude, longitude, photo_url, date, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, story, latitude, longitude, photo_url, date, current_user.id)
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for('home'))

    return render_template('add_memory.html')


@app.route('/edit_memory/<int:memory_id>', methods=['GET', 'POST'])
@login_required
def edit_memory(memory_id):
    conn = get_db_connection()
    memory = conn.execute('SELECT * FROM memory WHERE id = ?', (memory_id,)).fetchone()
    
    # Check ownership
    if memory is None or memory['user_id'] != current_user.id:
        conn.close()
        return redirect(url_for('home')) 
    
    # ... (inside edit_memory function) ...
    
    if request.method == 'POST':
        title = request.form['title']
        story = request.form['story']
        latitude = request.form['latitude']
        longitude = request.form['longitude']
        date = request.form['date']
        
        # Start with the existing photo URL
        photo_url = memory['photo_url'] 

        # --- FILE UPLOAD LOGIC (Same as add_memory, but updates photo_url) ---
        if 'photo' in request.files:
            file = request.files['photo']
            
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(filepath)
                
                # Update the photo_url with the new file path
                photo_url = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        # --- END FILE UPLOAD LOGIC ---

        # Update the database record
        conn.execute(
            """
            UPDATE memory SET title = ?, story = ?, latitude = ?, longitude = ?, 
            photo_url = ?, date = ? WHERE id = ?
            """,
            (title, story, latitude, longitude, photo_url, date, memory_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('home'))

# ... (rest of the edit_memory function) ...

    conn.close()
    # Convert Row to dict for the template
    return render_template('edit_memory.html', memory=dict(memory))


@app.route('/delete_memory/<int:memory_id>', methods=['POST'])
@login_required
def delete_memory(memory_id):
    conn = get_db_connection()
    memory = conn.execute('SELECT user_id FROM memory WHERE id = ?', (memory_id,)).fetchone()
    
    # Check ownership
    if memory is None or memory['user_id'] != current_user.id:
        conn.close()
        return redirect(url_for('home')) 

    conn.execute('DELETE FROM memory WHERE id = ?', (memory_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('home'))


@app.route('/appreciation', methods=['GET', 'POST'])
@login_required
def appreciation():
    if request.method == 'POST':
        text = request.form['text']
        author_id = current_user.id
        recipient_id = 1 if author_id == 2 else 2
        
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO appreciation (text, author_id, recipient_id) VALUES (?, ?, ?)",
            (text, author_id, recipient_id)
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for('appreciation'))
    
    conn = get_db_connection()
    appreciations = conn.execute(
        """
        SELECT a.id, a.text, u.username as author_name 
        FROM appreciation a 
        JOIN user u ON a.author_id = u.id 
        ORDER BY a.id DESC
        """
    ).fetchall()
    conn.close()
    
    # Convert rows to dicts for the template (good practice, though may not be necessary here)
    appreciations_list = [dict(row) for row in appreciations]

    return render_template('appreciation.html', appreciations=appreciations_list)

# --- EDIT APPRECIATION ROUTE ---
@app.route('/edit_appreciation/<int:note_id>', methods=['GET', 'POST'])
@login_required
def edit_appreciation(note_id):
    conn = get_db_connection()
    # Fetch the note
    note = conn.execute('SELECT * FROM appreciation WHERE id = ?', (note_id,)).fetchone()

    # CRUCIAL SECURITY CHECK: Ensure the note exists AND the current user wrote it
    if note is None or note['author_id'] != current_user.id:
        conn.close()
        return redirect(url_for('appreciation'))
    
    if request.method == 'POST':
        new_text = request.form['text']

        # Update the database record
        conn.execute(
            "UPDATE appreciation SET text = ? WHERE id = ?",
            (new_text, note_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('appreciation'))

    conn.close()
    # For GET request, render the edit form, pre-filled with the current data
    return render_template('edit_appreciation.html', note=dict(note))


# --- DELETE APPRECIATION ROUTE ---
@app.route('/delete_appreciation/<int:note_id>', methods=['POST'])
@login_required
def delete_appreciation(note_id):
    conn = get_db_connection()
    note = conn.execute('SELECT author_id FROM appreciation WHERE id = ?', (note_id,)).fetchone()
    
    # CRUCIAL SECURITY CHECK: Ensure the note exists AND the current user wrote it
    if note is None or note['author_id'] != current_user.id:
        conn.close()
        return redirect(url_for('appreciation')) 

    # Delete the record
    conn.execute('DELETE FROM appreciation WHERE id = ?', (note_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('appreciation'))


if __name__ == '__main__':
    # NOTE: You may need to delete the existing 'logbook.db' file 
    # if you change the password in .env and need to re-initialize the users.
    app.run(debug=True)
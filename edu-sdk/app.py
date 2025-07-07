import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import shutil

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key_here')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024  # 4GB limit

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# File model
class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    folder = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Folder model
class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неправильный логин или пароль')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Это имя пользователя уже занято')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация успешна! Теперь вы можете войти.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    selected_folder = request.args.get('folder', '')

    if request.method == 'POST' and 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            flash('Файл не выбран')
            return redirect(request.url)
        
        if file:
            folder_name = request.form.get('folder', '')
            user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id))
            
            # Create user directory if not exists
            os.makedirs(user_upload_dir, exist_ok=True)
            
            # Handle folder path
            if folder_name:
                folder_path = os.path.join(user_upload_dir, folder_name)
                os.makedirs(folder_path, exist_ok=True)
            
            filepath = os.path.join(user_upload_dir, folder_name if folder_name else '', file.filename)
            
            # Check if file already exists
            if os.path.exists(filepath):
                flash('Файл с таким именем уже существует')
                return redirect(request.url)
            
            file.save(filepath)

            new_file = File(
                filename=file.filename,
                folder=folder_name if folder_name else None,
                user_id=current_user.id
            )
            db.session.add(new_file)
            db.session.commit()
            flash('Файл успешно загружен.')
            return redirect(url_for('dashboard', folder=selected_folder))

    user_folders = Folder.query.filter_by(user_id=current_user.id).all()
    user_files = File.query.filter_by(
        user_id=current_user.id,
        folder=selected_folder if selected_folder else None
    ).all()

    return render_template(
        'dashboard.html',
        files=user_files,
        folders=user_folders,
        selected_folder=selected_folder
    )

@app.route('/create_folder', methods=['POST'])
@login_required
def create_folder():
    folder_name = request.form.get('folder_name', '').strip()
    if not folder_name:
        flash('Имя папки не может быть пустым')
        return redirect(url_for('dashboard'))
    
    # Check if folder already exists
    existing_folder = Folder.query.filter_by(
        name=folder_name,
        user_id=current_user.id
    ).first()
    if existing_folder:
        flash('Папка с таким именем уже существует')
        return redirect(url_for('dashboard'))
    
    folder_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        str(current_user.id),
        folder_name
    )
    os.makedirs(folder_path, exist_ok=True)

    new_folder = Folder(name=folder_name, user_id=current_user.id)
    db.session.add(new_folder)
    db.session.commit()
    flash('Папка создана.')

    return redirect(url_for('dashboard'))

@app.route('/delete_folder/<int:folder_id>', methods=['POST'])
@login_required
def delete_folder(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    if folder.user_id != current_user.id:
        flash('У вас нет прав на удаление этой папки')
        return redirect(url_for('dashboard'))

    folder_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        str(current_user.id),
        folder.name
    )
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

    File.query.filter_by(
        user_id=current_user.id,
        folder=folder.name
    ).delete()
    db.session.delete(folder)
    db.session.commit()

    flash('Папка удалена.')
    return redirect(url_for('dashboard'))

@app.route('/delete_file/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    file_to_delete = File.query.get_or_404(file_id)
    if file_to_delete.user_id != current_user.id:
        flash('У вас нет прав на удаление этого файла')
        return redirect(url_for('dashboard'))

    file_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        str(current_user.id),
        file_to_delete.folder if file_to_delete.folder else '',
        file_to_delete.filename
    )
    if os.path.exists(file_path):
        os.remove(file_path)

    db.session.delete(file_to_delete)
    db.session.commit()

    flash('Файл успешно удалён')
    return redirect(url_for('dashboard', folder=file_to_delete.folder if file_to_delete.folder else ''))

@app.route('/download/<folder>/<filename>')
@login_required
def download_file(folder, filename):
    if folder == 'None':
        folder = ''
    
    user_folder = os.path.join(
        app.config['UPLOAD_FOLDER'],
        str(current_user.id),
        folder
    )
    
    file_path = os.path.join(user_folder, filename)
    if not os.path.exists(file_path):
        flash('Файл не найден')
        return redirect(url_for('dashboard'))
    
    file_record = File.query.filter_by(
        filename=filename,
        folder=folder if folder else None,
        user_id=current_user.id
    ).first()
    if not file_record:
        flash('У вас нет прав доступа к этому файлу')
        return redirect(url_for('dashboard'))
    
    return send_from_directory(
        directory=user_folder,
        path=filename,
        as_attachment=True
    )

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

if __name__ == '__main__':
    # Create uploads directory if not exists
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    with app.app_context():
        db.create_all()

    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

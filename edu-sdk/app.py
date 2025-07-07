import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename  # Добавлен этот импорт
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
app.config['ALLOWED_EXTENSIONS'] = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx'}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    folder = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
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
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            folder_name = request.form.get('folder', '')
            
            user_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id))
            os.makedirs(user_folder, exist_ok=True)
            
            if folder_name:
                folder_path = os.path.join(user_folder, folder_name)
                os.makedirs(folder_path, exist_ok=True)
                filepath = os.path.join(folder_path, filename)
            else:
                filepath = os.path.join(user_folder, filename)
            
            if os.path.exists(filepath):
                flash('Файл с таким именем уже существует')
                return redirect(request.url)
            
            try:
                file.save(filepath)
                new_file = File(
                    filename=filename,
                    folder=folder_name if folder_name else None,
                    user_id=current_user.id
                )
                db.session.add(new_file)
                db.session.commit()
                flash('Файл успешно загружен.')
            except Exception as e:
                flash(f'Ошибка при загрузке файла: {str(e)}')
            
            return redirect(url_for('dashboard', folder=selected_folder))
        else:
            flash('Недопустимый тип файла')

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
    
    existing_folder = Folder.query.filter_by(
        name=folder_name,
        user_id=current_user.id
    ).first()
    if existing_folder:
        flash('Папка с таким именем уже существует')
        return redirect(url_for('dashboard'))
    
    try:
        folder_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            str(current_user.id),
            folder_name
        )
        os.makedirs(folder_path, exist_ok=True)
        
        new_folder = Folder(name=folder_name, user_id=current_user.id)
        db.session.add(new_folder)
        db.session.commit()
        flash('Папка успешно создана')
    except Exception as e:
        flash(f'Ошибка при создании папки: {str(e)}')
    
    return redirect(url_for('dashboard'))

@app.route('/delete_folder/<int:folder_id>', methods=['POST'])
@login_required
def delete_folder(folder_id):
    folder = db.session.get(Folder, folder_id)
    if not folder or folder.user_id != current_user.id:
        flash('У вас нет прав на удаление этой папки')
        return redirect(url_for('dashboard'))

    try:
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
        flash('Папка успешно удалена')
    except Exception as e:
        flash(f'Ошибка при удалении папки: {str(e)}')
    
    return redirect(url_for('dashboard'))

@app.route('/delete_file/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    file_to_delete = db.session.get(File, file_id)
    if not file_to_delete or file_to_delete.user_id != current_user.id:
        flash('У вас нет прав на удаление этого файла')
        return redirect(url_for('dashboard'))

    try:
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
    except Exception as e:
        flash(f'Ошибка при удалении файла: {str(e)}')
    
    return redirect(url_for('dashboard', folder=file_to_delete.folder if file_to_delete.folder else ''))

@app.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    file_record = db.session.get(File, file_id)
    if not file_record or file_record.user_id != current_user.id:
        flash('У вас нет прав доступа к этому файлу')
        return redirect(url_for('dashboard'))

    try:
        file_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            str(current_user.id),
            file_record.folder if file_record.folder else '',
            file_record.filename
        )
        
        if not os.path.exists(file_path):
            flash('Файл не найден')
            return redirect(url_for('dashboard'))
        
        directory = os.path.join(
            app.config['UPLOAD_FOLDER'],
            str(current_user.id),
            file_record.folder if file_record.folder else ''
        )
        return send_from_directory(
            directory=directory,
            path=file_record.filename,
            as_attachment=True
        )
    except Exception as e:
        flash(f'Ошибка при скачивании файла: {str(e)}')
        return redirect(url_for('dashboard'))

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
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    with app.app_context():
        db.create_all()

    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

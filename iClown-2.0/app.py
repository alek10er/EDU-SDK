from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024 * 1024
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)

# Модель пользователя
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# Модель файла
class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Неправильный логин или пароль')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
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
    if request.method == 'POST':
        file = request.files['file']
        if file:
            filename = file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Проверяем, что файл действительно был загружен полностью
            if os.path.exists(filepath):
                new_file = File(filename=filename, user_id=current_user.id)
                db.session.add(new_file)
                db.session.commit()
                flash('Файл успешно загружен.')
            else:
                flash('Ошибка при загрузке файла. Попробуйте снова.')
    user_files = File.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', files=user_files)

@app.route('/delete/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    file_to_delete = File.query.get_or_404(file_id)
    # Проверяем, что файл принадлежит текущему пользователю
    if file_to_delete.user_id != current_user.id:
        flash('У вас нет прав на удаление этого файла')
        return redirect(url_for('dashboard'))
    
    # Удаляем файл с диска
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_to_delete.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # Удаляем запись из базы данных
    db.session.delete(file_to_delete)
    db.session.commit()
    
    flash('Файл успешно удалён')
    return redirect(url_for('dashboard'))

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Создаем контекст приложения
    with app.app_context():
        # Создание базы данных и всех таблиц
        db.create_all()

        # Проверяем, есть ли пользователи в базе данных
        if not User.query.first():
            # Если пользователей нет, создаем пользователя admin
            admin_password = generate_password_hash('admin', method='pbkdf2:sha256')
            admin_user = User(username='admin', password=admin_password)
            db.session.add(admin_user)
            db.session.commit()
            print("Создан пользователь admin с паролем admin")

    # Запуск приложения
    app.run(host='0.0.0.0', port=80, debug=True)


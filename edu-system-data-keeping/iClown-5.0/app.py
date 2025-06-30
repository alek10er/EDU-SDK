from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import shutil

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024 * 1024  # limut is 200GB
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)

# user model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# file model
class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    folder = db.Column(db.String(100), nullable=True)  # Adding folder support
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Folder model
class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
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
    selected_folder = request.args.get('folder', '')

    if request.method == 'POST':
        file = request.files['file']
        folder_name = request.form.get('folder', '')
        if file:
            folder_path = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id), folder_name)
            os.makedirs(folder_path, exist_ok=True)

            filepath = os.path.join(folder_path, file.filename)
            file.save(filepath)

            new_file = File(filename=file.filename, folder=folder_name, user_id=current_user.id)
            db.session.add(new_file)
            db.session.commit()
            flash('Файл успешно загружен.')

    user_folders = Folder.query.filter_by(user_id=current_user.id).all()
    user_files = File.query.filter_by(user_id=current_user.id, folder=selected_folder).all()

    return render_template('dashboard.html', files=user_files, folders=user_folders, selected_folder=selected_folder)

@app.route('/create_folder', methods=['POST'])
@login_required
def create_folder():
    folder_name = request.form['folder_name']
    if folder_name:
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id), folder_name)
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

    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id), folder.name)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

    File.query.filter_by(user_id=current_user.id, folder=folder.name).delete()
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

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id), file_to_delete.folder, file_to_delete.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    db.session.delete(file_to_delete)
    db.session.commit()

    flash('Файл успешно удалён')
    return redirect(url_for('dashboard'))

@app.route('/download/<folder>/<filename>')
@login_required
def download_file(folder, filename):
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id), folder)
    return send_from_directory(user_folder, filename)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(host='0.0.0.0', port=80, debug=True)

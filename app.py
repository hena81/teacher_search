import os
import uuid
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired
import pandas as pd
from io import BytesIO
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max file size
app.config['LOGO_UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(app.config['LOGO_UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'يرجى تسجيل الدخول للوصول لهذه الصفحة'
login_manager.login_message_category = 'error'

# Database Models
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    civil_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Settings(db.Model):
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.String(500))
    
    @staticmethod
    def get_value(key, default=None):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @staticmethod
    def set_value(key, value):
        setting = Settings.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Settings(key=key, value=value)
            db.session.add(setting)
        db.session.commit()

# ── Context processor: inject site settings into every template ──────────────
@app.context_processor
def inject_site_settings():
    school_name = Settings.get_value('school_name', 'ثانوية عبدالعزيز سعود البابطين')
    site_title  = Settings.get_value('site_title',  'توزيع المعلمين على لجان اختبارات الفترة الدراسية الأولى\nللعام الدراسي 2025-2026')
    logo_file   = Settings.get_value('logo_filename', None)
    if logo_file:
        logo_url = url_for('serve_logo', filename=logo_file)
    else:
        logo_url = url_for('static', filename='logo.png')
    return dict(site_school_name=school_name, site_title=site_title, site_logo_url=logo_url)


class Assignment(db.Model):
    __tablename__ = 'assignments'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    civil_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200))
    department = db.Column(db.String(200))
    assignment = db.Column(db.String(200))
    main_committee = db.Column(db.String(200))
    sub_committee = db.Column(db.String(200))
    location = db.Column(db.String(200))
    day = db.Column(db.String(50))
    date = db.Column(db.String(20))
    
    def to_dict(self):
        return {
            'id': self.id,
            'civil_no': self.civil_no,
            'name': self.name,
            'department': self.department,
            'assignment': self.assignment,
            'main_committee': self.main_committee,
            'sub_committee': self.sub_committee,
            'location': self.location,
            'day': self.day,
            'date': self.date
        }

# Forms
class SearchForm(FlaskForm):
    civil_no = StringField('الرقم المدني', validators=[DataRequired(message='يرجى إدخال الرقم المدني')])

class LoginForm(FlaskForm):
    civil_no = StringField('الرقم المدني', validators=[DataRequired(message='يرجى إدخال الرقم المدني')])
    password = PasswordField('كلمة المرور', validators=[DataRequired(message='يرجى إدخال كلمة المرور')])

class RegisterForm(FlaskForm):
    civil_no = StringField('الرقم المدني', validators=[DataRequired(message='يرجى إدخال الرقم المدني')])
    name = StringField('الاسم', validators=[DataRequired(message='يرجى إدخال الاسم')])
    password = PasswordField('كلمة المرور', validators=[DataRequired(message='يرجى إدخال كلمة المرور')])

class ChangePasswordForm(FlaskForm):
    new_password = PasswordField('كلمة المرور الجديدة', validators=[DataRequired(message='يرجى إدخال كلمة المرور الجديدة')])

class UploadForm(FlaskForm):
    file = FileField('ملف Excel', validators=[
        FileAllowed(['xlsx', 'xls'], 'يُسمح فقط بملفات Excel (.xlsx, .xls)')
    ])

# Required Excel columns mapping
REQUIRED_COLUMNS = {
    'الرقم المدني': 'civil_no',
    'الاسم': 'name',
    'القسم': 'department',
    'التكليف': 'assignment',
    'اللجنة الرئيسية': 'main_committee',
    'اللجنة الفرعية': 'sub_committee',
    'موقع اللجنة': 'location',
    'اليوم': 'day',
    'التاريخ': 'date'
}

# ── Logo serving route ────────────────────────────────────────────────────────
@app.route('/uploads/<path:filename>')
def serve_logo(filename):
    return send_file(os.path.join(app.config['LOGO_UPLOAD_FOLDER'], filename))

# ── Site settings API ──────────────────────────────────────────────────────────
@app.route('/api/site_settings', methods=['POST'])
@login_required
def api_save_site_settings():
    """Save site title, school name, and optionally a new logo."""
    try:
        school_name = request.form.get('school_name', '').strip()
        site_title  = request.form.get('site_title',  '').strip()
        if school_name:
            Settings.set_value('school_name', school_name)
        if site_title:
            Settings.set_value('site_title', site_title)

        # Handle logo upload
        logo = request.files.get('logo')
        if logo and logo.filename:
            ext = os.path.splitext(logo.filename)[1].lower()
            if ext not in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'):
                flash('صيغة الشعار غير مدعومة. استخدم PNG أو JPG أو SVG.', 'error')
                return redirect(url_for('upload'))
            filename = f'logo_{uuid.uuid4().hex}{ext}'
            logo.save(os.path.join(app.config['LOGO_UPLOAD_FOLDER'], filename))
            # Delete old custom logo if exists
            old = Settings.get_value('logo_filename')
            if old:
                old_path = os.path.join(app.config['LOGO_UPLOAD_FOLDER'], old)
                if os.path.exists(old_path):
                    os.remove(old_path)
            Settings.set_value('logo_filename', filename)

        flash('تم حفظ إعدادات الموقع بنجاح ✅', 'success')
    except Exception as e:
        flash(f'حدث خطأ: {str(e)}', 'error')
    return redirect(url_for('upload'))

# Routes
@app.route('/offline')
def offline():
    return render_template('offline.html')

@app.route('/')
def index():
    return redirect(url_for('search'))

@app.route('/search', methods=['GET', 'POST'])
def search():
    form = SearchForm()
    results = []
    searched = False
    civil_no = ''
    search_enabled = Settings.get_value('search_enabled', 'true') == 'true'
    
    if request.method == 'POST' and form.validate_on_submit():
        civil_no = form.civil_no.data.strip()
        searched = True
        if search_enabled:
            results = Assignment.query.filter_by(civil_no=civil_no).all()
    
    return render_template('search.html', form=form, results=results, searched=searched, civil_no=civil_no, search_enabled=search_enabled)

@app.route('/api/search')
def api_search():
    civil_no = request.args.get('civil', '').strip()
    if not civil_no:
        return jsonify({'error': 'يرجى إدخال الرقم المدني', 'results': []}), 400
    
    results = Assignment.query.filter_by(civil_no=civil_no).all()
    return jsonify({
        'civil_no': civil_no,
        'count': len(results),
        'results': [r.to_dict() for r in results]
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('upload'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        civil_no = form.civil_no.data.strip()
        password = form.password.data
        
        user = User.query.filter_by(civil_no=civil_no).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('تم تسجيل الدخول بنجاح', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('upload'))
        else:
            flash('الرقم المدني أو كلمة المرور غير صحيحة', 'error')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('search'))

@app.route('/users', methods=['GET', 'POST'])
@login_required
def users():
    register_form = RegisterForm()
    change_password_form = ChangePasswordForm()
    users_list = User.query.all()
    
    return render_template('users.html', 
                         register_form=register_form, 
                         change_password_form=change_password_form,
                         users=users_list)

@app.route('/users/add', methods=['POST'])
@login_required
def add_user():
    form = RegisterForm()
    if form.validate_on_submit():
        civil_no = form.civil_no.data.strip()
        name = form.name.data.strip()
        password = form.password.data
        
        # Check if user already exists
        existing_user = User.query.filter_by(civil_no=civil_no).first()
        if existing_user:
            flash('الرقم المدني مسجل مسبقاً', 'error')
            return redirect(url_for('users'))
        
        # Create new user
        new_user = User(civil_no=civil_no, name=name, is_admin=False)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash(f'تم إضافة المستخدم "{name}" بنجاح', 'success')
    else:
        flash('يرجى ملء جميع الحقول المطلوبة', 'error')
    
    return redirect(url_for('users'))

@app.route('/users/change_password/<int:user_id>', methods=['POST'])
@login_required
def change_password(user_id):
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '').strip()
    
    if not new_password:
        flash('يرجى إدخال كلمة المرور الجديدة', 'error')
        return redirect(url_for('users'))
    
    user.set_password(new_password)
    db.session.commit()
    flash(f'تم تغيير كلمة المرور للمستخدم "{user.name}" بنجاح', 'success')
    
    return redirect(url_for('users'))

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        flash('لا يمكنك حذف حسابك الحالي', 'error')
        return redirect(url_for('users'))
    
    name = user.name
    db.session.delete(user)
    db.session.commit()
    flash(f'تم حذف المستخدم "{name}" بنجاح', 'success')
    
    return redirect(url_for('users'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = UploadForm()
    
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('لم يتم اختيار ملف', 'error')
            return redirect(url_for('upload'))
        
        file = request.files['file']
        if file.filename == '':
            flash('لم يتم اختيار ملف', 'error')
            return redirect(url_for('upload'))
        
        if file and file.filename.endswith(('.xlsx', '.xls')):
            try:
                # Read Excel file
                df = pd.read_excel(file)
                
                # Check for required columns
                missing_columns = []
                for col in REQUIRED_COLUMNS.keys():
                    if col not in df.columns:
                        missing_columns.append(col)
                
                if missing_columns:
                    flash(f'الأعمدة التالية مفقودة في الملف: {", ".join(missing_columns)}', 'error')
                    return redirect(url_for('upload'))
                
                # Process and insert/update records
                added = 0
                updated = 0
                
                for _, row in df.iterrows():
                    civil_no = str(row['الرقم المدني']).strip()
                    if not civil_no or civil_no == 'nan':
                        continue
                    
                    # Check if record exists
                    existing = Assignment.query.filter_by(civil_no=civil_no).first()
                    
                    if existing:
                        # Update existing record
                        existing.name = str(row.get('الاسم', '')).strip() if pd.notna(row.get('الاسم')) else ''
                        existing.department = str(row.get('القسم', '')).strip() if pd.notna(row.get('القسم')) else ''
                        existing.assignment = str(row.get('التكليف', '')).strip() if pd.notna(row.get('التكليف')) else ''
                        existing.main_committee = str(row.get('اللجنة الرئيسية', '')).strip() if pd.notna(row.get('اللجنة الرئيسية')) else ''
                        existing.sub_committee = str(row.get('اللجنة الفرعية', '')).strip() if pd.notna(row.get('اللجنة الفرعية')) else ''
                        existing.location = str(row.get('موقع اللجنة', '')).strip() if pd.notna(row.get('موقع اللجنة')) else ''
                        existing.day = str(row.get('اليوم', '')).strip() if pd.notna(row.get('اليوم')) else ''
                        date_val = row.get('التاريخ', '')
                        if pd.notna(date_val):
                            if isinstance(date_val, datetime):
                                existing.date = date_val.strftime('%Y-%m-%d')
                            else:
                                existing.date = str(date_val).strip()
                        else:
                            existing.date = ''
                        updated += 1
                    else:
                        # Add new record
                        date_val = row.get('التاريخ', '')
                        if pd.notna(date_val):
                            if isinstance(date_val, datetime):
                                date_str = date_val.strftime('%Y-%m-%d')
                            else:
                                date_str = str(date_val).strip()
                        else:
                            date_str = ''
                        
                        new_assignment = Assignment(
                            civil_no=civil_no,
                            name=str(row.get('الاسم', '')).strip() if pd.notna(row.get('الاسم')) else '',
                            department=str(row.get('القسم', '')).strip() if pd.notna(row.get('القسم')) else '',
                            assignment=str(row.get('التكليف', '')).strip() if pd.notna(row.get('التكليف')) else '',
                            main_committee=str(row.get('اللجنة الرئيسية', '')).strip() if pd.notna(row.get('اللجنة الرئيسية')) else '',
                            sub_committee=str(row.get('اللجنة الفرعية', '')).strip() if pd.notna(row.get('اللجنة الفرعية')) else '',
                            location=str(row.get('موقع اللجنة', '')).strip() if pd.notna(row.get('موقع اللجنة')) else '',
                            day=str(row.get('اليوم', '')).strip() if pd.notna(row.get('اليوم')) else '',
                            date=date_str
                        )
                        db.session.add(new_assignment)
                        added += 1
                
                db.session.commit()
                flash(f'تم رفع الملف بنجاح! تمت إضافة {added} سجل وتحديث {updated} سجل.', 'success')
                
            except Exception as e:
                db.session.rollback()
                flash(f'حدث خطأ أثناء معالجة الملف: {str(e)}', 'error')
        else:
            flash('يُسمح فقط بملفات Excel (.xlsx, .xls)', 'error')
        
        return redirect(url_for('upload'))
    
    return render_template('upload.html', form=form)

@app.route('/api/assignments')
def api_assignments():
    assignments = Assignment.query.all()
    return jsonify({
        'count': len(assignments),
        'data': [a.to_dict() for a in assignments]
    })

@app.route('/api/delete_all', methods=['POST'])
def api_delete_all():
    try:
        num_deleted = Assignment.query.delete()
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'تم حذف {num_deleted} سجل بنجاح',
            'deleted_count': num_deleted
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        }), 500

@app.route('/api/search_status')
@login_required
def api_search_status():
    """Get the current search enabled status"""
    search_enabled = Settings.get_value('search_enabled', 'true') == 'true'
    return jsonify({
        'success': True,
        'search_enabled': search_enabled
    })

@app.route('/api/toggle_search', methods=['POST'])
@login_required
def api_toggle_search():
    """Toggle the search enabled status"""
    try:
        current_status = Settings.get_value('search_enabled', 'true')
        new_status = 'false' if current_status == 'true' else 'true'
        Settings.set_value('search_enabled', new_status)
        
        status_text = 'مفعّل' if new_status == 'true' else 'متوقف'
        return jsonify({
            'success': True,
            'search_enabled': new_status == 'true',
            'message': f'تم تغيير حالة البحث إلى: {status_text}'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        }), 500


@app.route('/api/template')
def api_template():
    # Create Excel template
    df = pd.DataFrame(columns=list(REQUIRED_COLUMNS.keys()))
    
    # Add sample row
    sample_data = {
        'الرقم المدني': '123456789',
        'الاسم': 'أحمد محمد',
        'القسم': 'الرياضيات',
        'التكليف': 'ملاحظ',
        'اللجنة الرئيسية': 'اللجنة أ',
        'اللجنة الفرعية': 'الفرعية 1',
        'موقع اللجنة': 'قاعة 101',
        'اليوم': 'الأحد',
        'التاريخ': '2025-01-15'
    }
    df = pd.concat([df, pd.DataFrame([sample_data])], ignore_index=True)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='البيانات')
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='template.xlsx'
    )

@app.route('/api/export')
def api_export():
    assignments = Assignment.query.all()
    
    data = []
    for a in assignments:
        data.append({
            'الرقم المدني': a.civil_no,
            'الاسم': a.name,
            'القسم': a.department,
            'التكليف': a.assignment,
            'اللجنة الرئيسية': a.main_committee,
            'اللجنة الفرعية': a.sub_committee,
            'موقع اللجنة': a.location,
            'اليوم': a.day,
            'التاريخ': a.date
        })
    
    df = pd.DataFrame(data)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='البيانات')
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'assignments_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

# Create database tables and add sample data
def init_db():
    with app.app_context():
        db.create_all()
        
        # Add default admin user if no users exist
        if User.query.count() == 0:
            admin = User(civil_no='admin', name='مدير النظام', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('تم إنشاء مستخدم افتراضي: الرقم المدني: admin, كلمة المرور: admin123')
        
        # Add sample data if empty
        if Assignment.query.count() == 0:
            sample_data = [
                Assignment(
                    civil_no='281010100001',
                    name='أحمد محمد العلي',
                    department='الرياضيات',
                    assignment='ملاحظ رئيسي',
                    main_committee='اللجنة الأولى',
                    sub_committee='الفرعية أ',
                    location='قاعة 101 - المبنى الرئيسي',
                    day='الأحد',
                    date='2025-01-15'
                ),
                Assignment(
                    civil_no='281010100002',
                    name='خالد سعد الفهد',
                    department='اللغة العربية',
                    assignment='ملاحظ',
                    main_committee='اللجنة الثانية',
                    sub_committee='الفرعية ب',
                    location='قاعة 205 - المبنى الشرقي',
                    day='الاثنين',
                    date='2025-01-16'
                ),
                Assignment(
                    civil_no='281010100003',
                    name='عبدالله ناصر الحمد',
                    department='العلوم',
                    assignment='ملاحظ احتياطي',
                    main_committee='اللجنة الأولى',
                    sub_committee='الفرعية ج',
                    location='قاعة 103 - المبنى الرئيسي',
                    day='الثلاثاء',
                    date='2025-01-17'
                ),
                Assignment(
                    civil_no='281010100004',
                    name='محمد علي السالم',
                    department='اللغة الإنجليزية',
                    assignment='رئيس لجنة',
                    main_committee='اللجنة الثالثة',
                    sub_committee='الفرعية أ',
                    location='قاعة 301 - المبنى الغربي',
                    day='الأربعاء',
                    date='2025-01-18'
                ),
                Assignment(
                    civil_no='281010100005',
                    name='فهد عبدالرحمن الشمري',
                    department='التربية الإسلامية',
                    assignment='ملاحظ',
                    main_committee='اللجنة الثانية',
                    sub_committee='الفرعية د',
                    location='قاعة 207 - المبنى الشرقي',
                    day='الخميس',
                    date='2025-01-19'
                )
            ]
            
            for assignment in sample_data:
                db.session.add(assignment)
            
            db.session.commit()
            print('تم إنشاء قاعدة البيانات وإضافة بيانات تجريبية')

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)

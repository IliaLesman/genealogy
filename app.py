from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'odessa-genealogy-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///genealogy.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix for Render.com PostgreSQL URL (postgres:// -> postgresql://)
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

db = SQLAlchemy(app)

# ─── МОДЕЛИ ────────────────────────────────────────────────────────────────────

class Person(db.Model):
    __tablename__ = 'persons'
    id            = db.Column(db.Integer, primary_key=True)
    last_name     = db.Column(db.String(100), nullable=False)
    first_name    = db.Column(db.String(100), nullable=False)
    middle_name   = db.Column(db.String(100))
    birth_year    = db.Column(db.Integer)
    birth_place   = db.Column(db.String(200))
    death_year    = db.Column(db.Integer)
    notes         = db.Column(db.Text)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    # Связи
    relations_as_person1 = db.relationship('Relation', foreign_keys='Relation.person1_id', backref='person1', lazy=True)
    relations_as_person2 = db.relationship('Relation', foreign_keys='Relation.person2_id', backref='person2', lazy=True)

    def to_dict(self):
        return {
            'id':          self.id,
            'last_name':   self.last_name,
            'first_name':  self.first_name,
            'middle_name': self.middle_name or '',
            'birth_year':  self.birth_year,
            'birth_place': self.birth_place or '',
            'death_year':  self.death_year,
            'notes':       self.notes or '',
            'full_name':   f"{self.last_name} {self.first_name} {self.middle_name or ''}".strip()
        }

    def get_relatives(self):
        relatives = []
        for rel in self.relations_as_person1:
            p = Person.query.get(rel.person2_id)
            if p:
                relatives.append({'person': p.to_dict(), 'relation_type': rel.relation_type, 'direction': 'out'})
        for rel in self.relations_as_person2:
            p = Person.query.get(rel.person1_id)
            if p:
                relatives.append({'person': p.to_dict(), 'relation_type': rel.relation_type, 'direction': 'in'})
        return relatives


class Relation(db.Model):
    __tablename__ = 'relations'
    id            = db.Column(db.Integer, primary_key=True)
    person1_id    = db.Column(db.Integer, db.ForeignKey('persons.id'), nullable=False)
    person2_id    = db.Column(db.Integer, db.ForeignKey('persons.id'), nullable=False)
    relation_type = db.Column(db.String(50), nullable=False)
    # Типы: отец, мать, сын, дочь, брат, сестра, муж, жена, дед, бабушка, внук, внучка


# ─── ПУБЛИЧНЫЕ СТРАНИЦЫ ────────────────────────────────────────────────────────

@app.route('/')
def index():
    total = Person.query.count()
    return render_template('index.html', total=total)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    results = Person.query.filter(
        or_(
            Person.last_name.ilike(f'%{query}%'),
            Person.first_name.ilike(f'%{query}%'),
            Person.middle_name.ilike(f'%{query}%'),
            Person.birth_place.ilike(f'%{query}%'),
        )
    ).limit(30).all()
    return jsonify([p.to_dict() for p in results])

@app.route('/person/<int:person_id>')
def person_page(person_id):
    person = Person.query.get_or_404(person_id)
    relatives = person.get_relatives()
    return render_template('person.html', person=person, relatives=relatives)

# ─── АВТОРИЗАЦИЯ ──────────────────────────────────────────────────────────────

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'odessa1794')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        return render_template('login.html', error='Неверный пароль')
    return render_template('login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ─── АДМИН-ПАНЕЛЬ ─────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_panel():
    persons = Person.query.order_by(Person.last_name).all()
    return render_template('admin.html', persons=persons)

@app.route('/admin/add_person', methods=['POST'])
@admin_required
def add_person():
    data = request.form
    person = Person(
        last_name   = data.get('last_name', '').strip(),
        first_name  = data.get('first_name', '').strip(),
        middle_name = data.get('middle_name', '').strip() or None,
        birth_year  = int(data['birth_year']) if data.get('birth_year') else None,
        birth_place = data.get('birth_place', '').strip() or None,
        death_year  = int(data['death_year']) if data.get('death_year') else None,
        notes       = data.get('notes', '').strip() or None,
    )
    db.session.add(person)
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/edit_person/<int:person_id>', methods=['POST'])
@admin_required
def edit_person(person_id):
    person = Person.query.get_or_404(person_id)
    data   = request.form
    person.last_name   = data.get('last_name', '').strip()
    person.first_name  = data.get('first_name', '').strip()
    person.middle_name = data.get('middle_name', '').strip() or None
    person.birth_year  = int(data['birth_year']) if data.get('birth_year') else None
    person.birth_place = data.get('birth_place', '').strip() or None
    person.death_year  = int(data['death_year']) if data.get('death_year') else None
    person.notes       = data.get('notes', '').strip() or None
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_person/<int:person_id>', methods=['POST'])
@admin_required
def delete_person(person_id):
    person = Person.query.get_or_404(person_id)
    Relation.query.filter(
        or_(Relation.person1_id == person_id, Relation.person2_id == person_id)
    ).delete()
    db.session.delete(person)
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/add_relation', methods=['POST'])
@admin_required
def add_relation():
    data = request.form
    rel = Relation(
        person1_id    = int(data['person1_id']),
        person2_id    = int(data['person2_id']),
        relation_type = data['relation_type'],
    )
    db.session.add(rel)
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_relation/<int:rel_id>', methods=['POST'])
@admin_required
def delete_relation(rel_id):
    rel = Relation.query.get_or_404(rel_id)
    db.session.delete(rel)
    db.session.commit()
    return redirect(url_for('admin_panel'))

# ─── API ──────────────────────────────────────────────────────────────────────

@app.route('/api/persons')
def api_persons():
    persons = Person.query.order_by(Person.last_name).all()
    return jsonify([p.to_dict() for p in persons])

# ─── ИНИЦИАЛИЗАЦИЯ ─────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)

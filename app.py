
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, scoped_session
import pandas as pd

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'panol.db')
EXCEL_PATH = next((p for p in [os.path.join(BASE_DIR, 'Base de datos Pañol.xlsx'), os.path.join(BASE_DIR, '..', 'Base de datos Pañol.xlsx')] if os.path.exists(p)), os.path.join(BASE_DIR, 'Base de datos Pañol.xlsx'))

app = Flask(__name__)
app.secret_key = 'demo-panol-2026'

engine = create_engine(f'sqlite:///' + DB_PATH, echo=False, future=True)
Session = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()

# --- MODELOS ---
class Role(Base):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

class User(Base, UserMixin):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    role_id = Column(Integer, ForeignKey('roles.id'))
    role = relationship('Role')

class Warehouse(Base):
    __tablename__ = 'warehouses'
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
    name = Column(String)

class Location(Base):
    __tablename__ = 'locations'
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)

class Supplier(Base):
    __tablename__ = 'suppliers'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

class Item(Base):
    __tablename__ = 'items'
    id = Column(Integer, primary_key=True)
    material = Column(String, unique=True)
    description = Column(Text)
    clas = Column(String)  # Clase ABC
    stock_min = Column(Float, default=0)
    stock = Column(Float, default=0)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'))
    warehouse = relationship('Warehouse')
    location_id = Column(Integer, ForeignKey('locations.id'))
    location = relationship('Location')

class Movement(Base):
    __tablename__ = 'movements'
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.utcnow)
    type = Column(String)  # IN, OUT, RETURN, ADJUST
    item_id = Column(Integer, ForeignKey('items.id'))
    item = relationship('Item')
    qty = Column(Float, default=0)
    user = Column(String)
    shift = Column(String)
    sector = Column(String)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=True)
    supplier = relationship('Supplier')
    remito = Column(String)
    factura = Column(String)
    observation = Column(Text)
    warehouse_from = Column(String)
    warehouse_to = Column(String)

Base.metadata.create_all(engine)

# --- LOGIN ---
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    db = Session()
    return db.query(User).get(int(user_id))

# --- SEED INICIAL ---

def seed_if_empty():
    db = Session()
    if db.query(Role).count() == 0:
        r1 = Role(name='keyuser'); r2 = Role(name='operador')
        db.add_all([r1,r2]); db.commit()
    if db.query(User).count() == 0:
        keyrole = db.query(Role).filter_by(name='keyuser').first()
        op = db.query(Role).filter_by(name='operador').first()
        db.add_all([
            User(username='ezequiel', password='demo123', role=keyrole),
            User(username='operador', password='demo123', role=op)
        ])
        db.commit()
    if db.query(Warehouse).count() == 0:
        db.add_all([
            Warehouse(code='101', name='Productos de Insumo'),
            Warehouse(code='800', name='Productos de Mantenimiento')
        ])
        db.commit()
    if db.query(Location).count() == 0 and os.path.exists(EXCEL_PATH):
        try:
            ubi = pd.read_excel(EXCEL_PATH, sheet_name='Base de Ubicaciones', engine='openpyxl')
            values = []
            for col in ubi.columns:
                values += [str(v).strip() for v in ubi[col].dropna().tolist() if isinstance(v, str) and v.strip() and not v.strip() in list('ABCDEFGH')]
            for code in sorted(set(values)):
                db.add(Location(code=code))
            db.commit()
        except Exception as e:
            print('No se pudo importar ubicaciones:', e)
    if db.query(Item).count() == 0 and os.path.exists(EXCEL_PATH):
        try:
            art = pd.read_excel(EXCEL_PATH, sheet_name='Maestro de Articulos ', engine='openpyxl')
            # Normalizar columnas
            art = art.rename(columns={'Texto breve material':'Descripcion', 'Clase':'Clase', 'Stock Min':'Stock Min'})
            art['Stock Min'] = art['Stock Min'].fillna(0)
            wh_101 = db.query(Warehouse).filter_by(code='101').first()
            for _, row in art.iterrows():
                mat = str(row.get('Material','')).strip()
                if not mat:
                    continue
                desc = str(row.get('Descripcion','')).strip()
                clas = str(row.get('Clase','')).strip() if not pd.isna(row.get('Clase')) else ''
                stock_min = float(row.get('Stock Min',0)) if not pd.isna(row.get('Stock Min')) else 0
                item = Item(material=mat, description=desc, clas=clas, stock_min=stock_min, stock=0, warehouse=wh_101)
                db.add(item)
            db.commit()
        except Exception as e:
            print('No se pudo importar artículos:', e)
    db.close()

seed_if_empty()

# --- HELPERS ---

def require_keyuser():
    if not current_user.is_authenticated or (current_user.role and current_user.role.name != 'keyuser'):
        flash('Necesita rol Key User para esta acción','warning')
        return False
    return True

# --- RUTAS ---
@app.route('/')
@login_required
def dashboard():
    db = Session()
    total_items = db.query(Item).count()
    low = db.query(Item).filter(Item.stock < Item.stock_min).count()
    total_stock = int(sum([i.stock for i in db.query(Item).all()]))
    last_moves = db.query(Movement).order_by(Movement.date.desc()).limit(10).all()
    return render_template('dashboard.html', total_items=total_items, low=low, total_stock=total_stock, last_moves=last_moves)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = Session()
        user = db.query(User).filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            flash('Bienvenido','success')
            return redirect(url_for('dashboard'))
        flash('Credenciales inválidas','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/turno', methods=['POST'])
@login_required
def turno():
    session['shift'] = request.form.get('shift','Mañana')
    return ('',204)

@app.route('/items')
@login_required
def items():
    db = Session()
    q = request.args.get('q','').strip()
    if q:
        rows = db.query(Item).filter((Item.material.contains(q)) | (Item.description.contains(q))).limit(500).all()
    else:
        rows = db.query(Item).limit(500).all()
    whs = db.query(Warehouse).all()
    locs = db.query(Location).limit(500).all()
    return render_template('items.html', items=rows, whs=whs, locs=locs, q=q)

@app.route('/items/new', methods=['POST'])
@login_required
def items_new():
    db = Session()
    material = request.form['material'].strip()
    if db.query(Item).filter_by(material=material).first():
        flash('El material ya existe','warning')
        return redirect(url_for('items'))
    desc = request.form.get('description','')
    clas = request.form.get('clas','')
    stock_min = float(request.form.get('stock_min','0') or 0)
    wh_id = request.form.get('warehouse_id')
    loc_id = request.form.get('location_id')
    item = Item(material=material, description=desc, clas=clas, stock_min=stock_min,
                warehouse_id=int(wh_id) if wh_id else None,
                location_id=int(loc_id) if loc_id else None)
    db.add(item); db.commit()
    flash('Código creado','success')
    return redirect(url_for('items'))

@app.route('/items/<int:item_id>/edit', methods=['POST'])
@login_required
def items_edit(item_id):
    db = Session(); item = db.query(Item).get(item_id)
    if not item: 
        flash('No encontrado','danger'); return redirect(url_for('items'))
    item.description = request.form.get('description', item.description)
    item.clas = request.form.get('clas', item.clas)
    item.stock_min = float(request.form.get('stock_min', item.stock_min) or 0)
    wh_id = request.form.get('warehouse_id')
    loc_id = request.form.get('location_id')
    item.warehouse_id = int(wh_id) if wh_id else None
    item.location_id = int(loc_id) if loc_id else None
    db.commit(); flash('Actualizado','success')
    return redirect(url_for('items'))

@app.route('/recepcion', methods=['GET','POST'])
@login_required
def recepcion():
    db = Session()
    if request.method == 'POST':
        material = request.form['material'].strip()
        qty = float(request.form.get('qty','0') or 0)
        supplier_name = request.form.get('supplier','').strip() or None
        remito = request.form.get('remito','')
        factura = request.form.get('factura','')
        obs = request.form.get('observation','')
        wh_to = request.form.get('warehouse_to','101')
        shift = session.get('shift','Mañana')
        item = db.query(Item).filter_by(material=material).first()
        if not item:
            flash('El código no existe. Créelo primero.','warning')
            return redirect(url_for('recepcion'))
        if supplier_name:
            supp = db.query(Supplier).filter_by(name=supplier_name).first()
            if not supp:
                supp = Supplier(name=supplier_name); db.add(supp); db.commit()
        else:
            supp = None
        item.stock += qty
        db.add(Movement(type='IN', item=item, qty=qty, user=current_user.username,
                        shift=shift, supplier=supp, remito=remito, factura=factura,
                        observation=obs, warehouse_to=wh_to))
        db.commit()
        flash(f'Entrada registrada (+{qty})','success')
        return redirect(url_for('recepcion'))
    whs = Session().query(Warehouse).all()
    return render_template('recepcion.html', whs=whs)

@app.route('/salidas', methods=['GET','POST'])
@login_required
def salidas():
    db = Session()
    if request.method == 'POST':
        material = request.form['material'].strip()
        qty = float(request.form.get('qty','0') or 0)
        sector = request.form.get('sector','')
        obs = request.form.get('observation','')
        wh_from = request.form.get('warehouse_from','101')
        shift = session.get('shift','Mañana')
        item = db.query(Item).filter_by(material=material).first()
        if not item:
            flash('El código no existe','warning'); return redirect(url_for('salidas'))
        if item.stock < qty:
            flash('Stock insuficiente: se registra pendiente','warning')
            qty = max(0, item.stock)
        item.stock -= qty
        db.add(Movement(type='OUT', item=item, qty=qty, user=current_user.username,
                        shift=shift, sector=sector, observation=obs, warehouse_from=wh_from))
        db.commit(); flash(f'Salida registrada (-{qty})','success')
        return redirect(url_for('salidas'))
    whs = Session().query(Warehouse).all()
    return render_template('salidas.html', whs=whs)

@app.route('/devoluciones', methods=['GET','POST'])
@login_required
def devoluciones():
    db = Session()
    if request.method == 'POST':
        material = request.form['material'].strip()
        qty = float(request.form.get('qty','0') or 0)
        obs = request.form.get('observation','')
        shift = session.get('shift','Mañana')
        item = db.query(Item).filter_by(material=material).first()
        if not item:
            flash('El código no existe','warning'); return redirect(url_for('devoluciones'))
        item.stock += qty
        db.add(Movement(type='RETURN', item=item, qty=qty, user=current_user.username,
                        shift=shift, observation=obs))
        db.commit(); flash(f'Devolución registrada (+{qty})','success')
        return redirect(url_for('devoluciones'))
    return render_template('devoluciones.html')

@app.route('/movimientos')
@login_required
def movimientos():
    db = Session()
    q = request.args.get('q','').strip()
    moves = db.query(Movement).order_by(Movement.date.desc())
    if q:
        moves = moves.join(Item).filter((Item.material.contains(q)) | (Item.description.contains(q)))
    moves = moves.limit(500).all()
    return render_template('movimientos.html', moves=moves, q=q)

@app.route('/alertas')
@login_required
def alertas():
    db = Session()
    rows = db.query(Item).filter(Item.stock < Item.stock_min).all()
    return render_template('alertas.html', rows=rows)

@app.route('/export/alertas.xlsx')
@login_required
def export_alertas():
    db = Session(); rows = db.query(Item).filter(Item.stock < Item.stock_min).all()
    df = pd.DataFrame([{ 'Material': r.material, 'Descripción': r.description, 'Stock actual': r.stock,
                         'Stock mínimo': r.stock_min, 'Almacén': (r.warehouse.code if r.warehouse else ''),
                         'Ubicación': (r.location.code if r.location else '') } for r in rows])
    path = os.path.join(BASE_DIR, 'alertas_quiebre.xlsx')
    if len(df)==0:
        df = pd.DataFrame(columns=['Material','Descripción','Stock actual','Stock mínimo','Almacén','Ubicación'])
    with pd.ExcelWriter(path, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Alertas')
    return send_file(path, as_attachment=True)

@app.route('/import', methods=['GET','POST'])
@login_required
def import_data():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash('Suba un archivo Excel','warning'); return redirect(url_for('import_data'))
        df = pd.read_excel(file, engine='openpyxl')
        # Esperado: Material, Descripción, Stock, Stock mínimo, Almacén, Ubicación
        from sqlalchemy import select
        db = Session()
        for _, row in df.iterrows():
            mat = str(row.get('Material','')).strip()
            if not mat: continue
            item = db.query(Item).filter_by(material=mat).first()
            if not item:
                item = Item(material=mat)
                db.add(item)
            item.description = str(row.get('Descripción','') or row.get('Descripcion','') or item.description)
            item.stock = float(row.get('Stock', item.stock) or 0)
            item.stock_min = float(row.get('Stock mínimo', item.stock_min) or row.get('Stock Min', item.stock_min) or 0)
            # Almacén
            wh_code = str(row.get('Almacén','') or '').strip()
            if wh_code:
                wh = db.query(Warehouse).filter_by(code=wh_code).first()
                if not wh:
                    wh = Warehouse(code=wh_code, name=f'Almacén {wh_code}')
                    db.add(wh); db.flush()
                item.warehouse = wh
            # Ubicación
            loc_code = str(row.get('Ubicación','') or '').strip()
            if loc_code:
                loc = db.query(Location).filter_by(code=loc_code).first()
                if not loc:
                    loc = Location(code=loc_code); db.add(loc); db.flush()
                item.location = loc
        db.commit(); flash('Importación completada','success')
        return redirect(url_for('items'))
    return render_template('import_export.html')



@app.route('/ajustes', methods=['GET','POST'])
@login_required
def ajustes():
    if not (current_user.is_authenticated and current_user.role and current_user.role.name=='keyuser'):
        flash('Solo Key User puede ajustar stock','warning'); return redirect(url_for('dashboard'))
    db = Session()
    if request.method=='POST':
        material = request.form['material'].strip()
        delta = float(request.form.get('delta','0') or 0)
        obs = request.form.get('observation','Ajuste manual')
        shift = session.get('shift','Mañana')
        item = db.query(Item).filter_by(material=material).first()
        if not item:
            flash('Código inexistente','danger'); return redirect(url_for('ajustes'))
        item.stock += delta
        db.add(Movement(type='ADJUST', item=item, qty=delta, user=current_user.username, shift=shift, observation=obs))
        db.commit(); flash('Ajuste aplicado','success'); return redirect(url_for('ajustes'))
    return render_template('ajustes.html')

# --- CONFIG SIMPLE (sólo Key User) ---
@app.route('/config')
@login_required
def config():
    if not require_keyuser():
        return redirect(url_for('dashboard'))
    db = Session()
    users = db.query(User).all(); roles = db.query(Role).all()
    whs = db.query(Warehouse).all()
    return render_template('config.html', users=users, roles=roles, whs=whs)

@app.route('/config/user', methods=['POST'])
@login_required
def config_user():
    if not require_keyuser():
        return redirect(url_for('config'))
    db = Session()
    username = request.form['username']; password = request.form.get('password','demo123')
    role_name = request.form.get('role','operador')
    role = db.query(Role).filter_by(name=role_name).first()
    if db.query(User).filter_by(username=username).first():
        flash('Usuario ya existe','warning')
    else:
        db.add(User(username=username, password=password, role=role))
        db.commit(); flash('Usuario creado','success')
    return redirect(url_for('config'))

@app.route('/config/warehouse', methods=['POST'])
@login_required
def config_wh():
    if not require_keyuser():
        return redirect(url_for('config'))
    db = Session()
    code = request.form['code']; name = request.form.get('name', f'Almacén {code}')
    if db.query(Warehouse).filter_by(code=code).first():
        flash('Almacén ya existe','warning')
    else:
        db.add(Warehouse(code=code, name=name)); db.commit(); flash('Almacén creado','success')
    return redirect(url_for('config'))

if __name__ == '__main__':
    app.run(debug=True)

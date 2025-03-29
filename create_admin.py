from app import app, db
from models import Usuario

def criar_admin():
    with app.app_context():
        # Cria as tabelas
        db.create_all()
        
        # Verifica se já existe um admin
        admin = Usuario.query.filter_by(username='admin').first()
        if not admin:
            admin = Usuario(username='admin', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Administrador criado com sucesso!')
        else:
            print('Administrador já existe!')

if __name__ == '__main__':
    criar_admin() 
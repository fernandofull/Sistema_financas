import os
from flask import Flask
from models import db, Usuario, Categoria

# Garante que o diretório instance existe
instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/financas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def init_db():
    with app.app_context():
        # Cria todas as tabelas
        db.create_all()
        
        # Cria usuário admin se não existir
        if not Usuario.query.filter_by(username='admin').first():
            admin = Usuario(username='admin', is_admin=True)
            admin.set_password('admin')  # Senha inicial: admin
            db.session.add(admin)
        
        # Cria categorias padrão
        categorias_despesa = [
            'Alimentação', 'Moradia', 'Transporte', 'Saúde', 'Educação',
            'Lazer', 'Vestuário', 'Higiene', 'Pets', 'Internet/Telefone',
            'Outros'
        ]
        
        categorias_receita = [
            'Salário', 'Freelance', 'Investimentos', 'Outros'
        ]
        
        # Adiciona categorias de despesa
        for nome in categorias_despesa:
            if not Categoria.query.filter_by(nome=nome, tipo='despesa').first():
                categoria = Categoria(nome=nome, tipo='despesa')
                db.session.add(categoria)
        
        # Adiciona categorias de receita
        for nome in categorias_receita:
            if not Categoria.query.filter_by(nome=nome, tipo='receita').first():
                categoria = Categoria(nome=nome, tipo='receita')
                db.session.add(categoria)
        
        # Commit das alterações
        db.session.commit()
        print("Banco de dados inicializado com sucesso!")

if __name__ == '__main__':
    init_db()

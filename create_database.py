from app import app, db
from models import Usuario
import os

def init_db():
    # Verifica se o banco de dados já existe
    db_path = 'instance/usuarios.db'
    if os.path.exists(db_path):
        print('Banco de dados já existe!')
        return
    
    # Cria o banco de dados e as tabelas
    with app.app_context():
        db.create_all()
        print('Banco de dados criado com sucesso!')

        # Cria o usuário administrador inicial
        print('\nVamos criar o usuário administrador inicial.')
        while True:
            username = input('Digite o nome do usuário admin: ').strip()
            if username:
                break
            print('Nome de usuário não pode estar vazio!')

        while True:
            password = input('Digite a senha do admin: ').strip()
            if len(password) >= 6:
                break
            print('A senha deve ter pelo menos 6 caracteres!')

        admin = Usuario(username=username, is_admin=True)
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        print(f'\nAdministrador "{username}" criado com sucesso!')
        print('Agora você pode iniciar a aplicação com "python app.py"')

if __name__ == '__main__':
    init_db() 
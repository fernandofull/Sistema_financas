import argparse
import os
from app import app, db
from models import Usuario, Categoria
from datetime import datetime

CATEGORIAS_DESPESAS = [
    'Alimentação',
    'Moradia',
    'Transporte',
    'Saúde',
    'Educação',
    'Lazer',
    'Vestuário',
    'Utilidades',
    'Outros'
]

CATEGORIAS_RECEITAS = [
    'Salário',
    'Freelance',
    'Investimentos',
    'Vendas',
    'Outros'
]

def criar_categorias():
    with app.app_context():
        # Criar categorias de despesas
        for cat in CATEGORIAS_DESPESAS:
            if not Categoria.query.filter_by(nome=cat, tipo='despesa').first():
                categoria = Categoria(nome=cat, tipo='despesa')
                db.session.add(categoria)

        # Criar categorias de receitas
        for cat in CATEGORIAS_RECEITAS:
            if not Categoria.query.filter_by(nome=cat, tipo='receita').first():
                categoria = Categoria(nome=cat, tipo='receita')
                db.session.add(categoria)

        db.session.commit()
        print('Categorias criadas com sucesso!')

def setup_system(username=None, password=None):
    # Verifica se o banco de dados já existe
    db_path = 'instance/financas.db'
    if os.path.exists(db_path):
        resposta = input('Banco de dados já existe! Deseja recriá-lo? (s/N): ').lower()
        if resposta != 's':
            print('Operação cancelada!')
            return
        os.remove(db_path)
    
    # Cria o banco de dados e as tabelas
    with app.app_context():
        print('Criando banco de dados...')
        db.create_all()
        print('Banco de dados criado com sucesso!')

        # Cria as categorias padrão
        criar_categorias()

        # Se não foram fornecidos username e password via argumentos
        if not username:
            while True:
                username = input('\nDigite o nome do usuário admin: ').strip()
                if len(username) >= 3 and ' ' not in username:
                    break
                print('Nome de usuário deve ter pelo menos 3 caracteres e não pode conter espaços!')

        if not password:
            while True:
                password = input('Digite a senha do admin: ').strip()
                if len(password) >= 6:
                    break
                print('A senha deve ter pelo menos 6 caracteres!')

        # Cria o usuário administrador
        admin = Usuario(username=username, is_admin=True)
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        print(f'\nAdministrador "{username}" criado com sucesso!')
        print('\nConfiguração concluída! Você pode agora:')
        print('1. Executar a aplicação com: python app.py')
        print(f'2. Fazer login com:\n   Usuário: {username}\n   Senha: {password}')

def main():
    parser = argparse.ArgumentParser(description='Configurar o sistema e criar admin')
    parser.add_argument('--username', '-u', help='Nome do usuário administrador')
    parser.add_argument('--password', '-p', help='Senha do administrador')
    
    args = parser.parse_args()
    
    setup_system(args.username, args.password)

if __name__ == '__main__':
    main()


# O script vai:
# Criar o banco de dados
# Criar o usuário administrador
# Mostrar as instruções para executar a aplicação
# Validações incluídas:
# Verifica se o banco já existe e pergunta se quer recriar
# Username deve ter pelo menos 3 caracteres e não pode ter espaços
# Senha deve ter pelo menos 6 caracteres
# Mostra mensagens claras de sucesso e próximos passos
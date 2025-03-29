import os
import sys

# Adiciona o diretório pai ao path do Python para poder importar o models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from models import db
from sqlalchemy import text

def upgrade():
    # Adiciona a coluna num_repeticoes à tabela despesas
    db.session.execute(text('ALTER TABLE despesas ADD COLUMN num_repeticoes INTEGER DEFAULT 12'))
    
    # Adiciona a coluna num_repeticoes à tabela receitas
    db.session.execute(text('ALTER TABLE receitas ADD COLUMN num_repeticoes INTEGER DEFAULT 12'))
    
    db.session.commit()

def downgrade():
    # Remove a coluna num_repeticoes da tabela despesas
    db.session.execute(text('ALTER TABLE despesas DROP COLUMN num_repeticoes'))
    
    # Remove a coluna num_repeticoes da tabela receitas
    db.session.execute(text('ALTER TABLE receitas DROP COLUMN num_repeticoes'))
    
    db.session.commit()

if __name__ == '__main__':
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/financas.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    with app.app_context():
        upgrade()

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from models import db, Usuario, Despesa, Receita, Categoria, ReservaInvestimento
from datetime import datetime, date
from functools import wraps
from flask_apscheduler import APScheduler
from dateutil.relativedelta import relativedelta
from sqlalchemy.sql import extract
from config import LIMITE_USUARIOS, EMAIL_CONTATO
import sys
import codecs
import os
import logging
from logging.handlers import RotatingFileHandler
import csv
import io

# Configura a codificação padrão para UTF-8
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuração do Logging
if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/financas.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Iniciando aplicação Finanças')

# Configuração do Scheduler
app.config['SCHEDULER_API_ENABLED'] = True
scheduler = APScheduler()

# Adicione no início do arquivo, junto com outras configurações
SENHA_ADMIN = "ApagarTudo"  # Você pode mudar para uma senha mais segura

db.init_app(app)

# Decorator para verificar se usuário está logado
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            flash('Acesso negado. Por favor, faça login para continuar.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator para verificar se usuário é admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session or not session.get('is_admin'):
            flash('Acesso negado. Apenas administradores podem acessar esta página!', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'usuario' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario' in session:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        senha = request.form.get('senha')
        
        usuario = Usuario.query.filter_by(username=username).first()
        
        if usuario and usuario.verificar_senha(senha):
            session['usuario'] = username
            session['is_admin'] = usuario.is_admin
            print(f"Login realizado: {username}, is_admin: {usuario.is_admin}")
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Usuário ou senha inválidos!', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/home')
@login_required
def home():
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = 'is_admin' in request.form
        
        if Usuario.query.filter_by(username=username).first():
            flash('Nome de usuário já existe!', 'danger')
        else:
            novo_usuario = Usuario(username=username, is_admin=is_admin)
            novo_usuario.set_password(password)
            db.session.add(novo_usuario)
            db.session.commit()
            flash('Usuário criado com sucesso!', 'success')
    
    usuarios = Usuario.query.all()
    return render_template('admin.html', usuarios=usuarios)

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    flash('Logout realizado com sucesso!', 'info')
    return redirect(url_for('login'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if not session.get('is_admin'):
        flash('Acesso negado!', 'danger')
        return redirect(url_for('home'))
    
    user = Usuario.query.get_or_404(user_id)
    
    # Impede que o admin exclua a si mesmo
    if user.username == session['usuario']:
        flash('Você não pode excluir seu próprio usuário!', 'danger')
        return redirect(url_for('admin'))
    
    try:
        db.session.delete(user)
        db.session.commit()
        flash(f'Usuário {user.username} excluído com sucesso!', 'success')
    except:
        db.session.rollback()
        flash('Erro ao excluir usuário!', 'danger')
    
    return redirect(url_for('admin'))

# No início do arquivo, após os imports
MESES = [
    'Janeiro',
    'Fevereiro',
    'Março',
    'Abril',
    'Maio',
    'Junho',
    'Julho',
    'Agosto',
    'Setembro',
    'Outubro',
    'Novembro',
    'Dezembro'
]

@app.route('/despesas', methods=['GET', 'POST'])
@login_required
def despesas():
    usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
    hoje = date.today()
    
    # Define período
    if request.method == 'POST':
        ano = int(request.form.get('ano', hoje.year))
        mes = int(request.form.get('mes', hoje.month))
    else:
        ano_param = request.args.get('ano', '')
        mes_param = request.args.get('mes', '')
        
        ano = int(ano_param) if ano_param.strip() else hoje.year
        mes = int(mes_param) if mes_param.strip() else hoje.month

    inicio = date(ano, mes, 1)
    fim = inicio + relativedelta(months=1, days=-1)

    # Configuração da paginação
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Número de itens por página
    
    # Parâmetro de ordenação
    sort_by = request.args.get('sort_by', 'status')  # Padrão é ordenar por status (pendentes primeiro)

    # Busca categorias
    categorias = Categoria.query.filter_by(tipo='despesa').all()
    
    # Processar o formulário de nova despesa
    if request.method == 'POST':
        try:
            app.logger.info('DEBUG: Obtendo valores do formulário...')
            descricao = request.form.get('descricao')
            valor = float(request.form.get('valor'))
            categoria_id = int(request.form.get('categoria'))
            data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
            fixa = request.form.get('fixa') == 'on'
            pago = request.form.get('pago') == 'on'
            num_repeticoes = int(request.form.get('num_repeticoes', 12))
            
            nova_despesa = Despesa(
                descricao=descricao,
                valor=valor,
                categoria_id=categoria_id,
                data=data,
                fixa=fixa,
                usuario_id=usuario_id,
                pago=pago,
                num_repeticoes=num_repeticoes
            )
            
            db.session.add(nova_despesa)
            db.session.commit()
            
            if fixa:
                replicar_lancamento_fixo('despesa', nova_despesa, usuario_id)
                
            flash('Despesa registrada com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Erro ao registrar despesa!', 'danger')
            print(str(e))
    
    # Query base
    query = Despesa.query.filter(
        Despesa.usuario_id == usuario_id,
        Despesa.data >= inicio,
        Despesa.data <= fim
    )
    
    # Aplica ordenação
    if sort_by == 'data':
        query = query.order_by(Despesa.data.asc())  # Modificado para asc()
    else:  # status é o padrão
        query = query.order_by(Despesa.pago.asc(), Despesa.data.desc())
    
    # Aplica paginação
    despesas = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('despesas.html',
                         despesas=despesas,
                         categorias=categorias,
                         anos=range(2024, hoje.year + 11),
                         meses=MESES,
                         mes_atual=mes,
                         ano_atual=ano,
                         hoje=hoje,
                         sort_by=sort_by)

@app.route('/receitas', methods=['GET', 'POST'])
@login_required
def receitas():
    usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
    hoje = date.today()
    
    # Define período
    if request.method == 'POST':
        ano = int(request.form.get('ano', hoje.year))
        mes = int(request.form.get('mes', hoje.month))
    else:
        ano_param = request.args.get('ano', '')
        mes_param = request.args.get('mes', '')
        
        ano = int(ano_param) if ano_param.strip() else hoje.year
        mes = int(mes_param) if mes_param.strip() else hoje.month

    inicio = date(ano, mes, 1)
    fim = inicio + relativedelta(months=1, days=-1)

    # Configuração da paginação
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Número de itens por página
    
    # Parâmetro de ordenação
    sort_by = request.args.get('sort_by', 'status')  # Padrão é ordenar por status (pendentes primeiro)

    # Busca categorias
    categorias = Categoria.query.filter_by(tipo='receita').all()
    
    if request.method == 'POST':
        try:
            app.logger.info('DEBUG: Obtendo valores do formulário...')
            descricao = request.form.get('descricao')
            valor = float(request.form.get('valor'))
            categoria_id = int(request.form.get('categoria'))
            data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
            fixa = request.form.get('fixa') == 'on'
            recebido = request.form.get('recebido') == 'on'
            num_repeticoes = int(request.form.get('num_repeticoes', 12))
            
            nova_receita = Receita(
                descricao=descricao,
                valor=valor,
                categoria_id=categoria_id,
                data=data,
                fixa=fixa,
                usuario_id=usuario_id,
                recebido=recebido,
                num_repeticoes=num_repeticoes
            )
            
            db.session.add(nova_receita)
            db.session.commit()
            
            if fixa:
                replicar_lancamento_fixo('receita', nova_receita, usuario_id)
                
            flash('Receita registrada com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Erro ao registrar receita!', 'danger')
            print(str(e))

    # Query base
    query = Receita.query.filter(
        Receita.usuario_id == usuario_id,
        Receita.data >= inicio,
        Receita.data <= fim
    )
    
    # Aplica ordenação
    if sort_by == 'data':
        query = query.order_by(Receita.data.asc())  # Modificado para asc()
    else:  # status é o padrão
        query = query.order_by(Receita.recebido.asc(), Receita.data.desc())
    
    # Aplica paginação
    receitas = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template('receitas.html',
                         receitas=receitas,
                         categorias=categorias,
                         anos=range(2024, hoje.year + 11),
                         meses=MESES,
                         mes_atual=mes,
                         ano_atual=ano,
                         hoje=hoje,
                         sort_by=sort_by)

@app.route('/balanco', methods=['GET', 'POST'])
@login_required
def balanco():
    usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
    hoje = date.today()
    
    # Define ano e mês
    ano_param = request.args.get('ano', '')
    mes_param = request.args.get('mes', '')
    
    ano = int(ano_param) if ano_param.strip() else hoje.year
    mes = int(mes_param) if mes_param.strip() else hoje.month

    # Define início e fim do período
    inicio = date(ano, mes, 1)
    fim = inicio + relativedelta(months=1, days=-1)

    try:
        # Processa ativos
        ativos_por_categoria = {}
        receitas = Receita.query.filter(
            Receita.usuario_id == usuario_id,
            Receita.data >= inicio,
            Receita.data <= fim,
            Receita.recebido == True
        ).all()

        for r in receitas:
            categoria = r.categoria.nome
            ativos_por_categoria[categoria] = ativos_por_categoria.get(categoria, 0) + float(r.valor)

        # Processa passivos
        passivos_por_categoria = {}
        despesas = Despesa.query.filter(
            Despesa.usuario_id == usuario_id,
            Despesa.data >= inicio,
            Despesa.data <= fim,
            Despesa.pago == True
        ).all()

        for d in despesas:
            categoria = d.categoria.nome
            passivos_por_categoria[categoria] = passivos_por_categoria.get(categoria, 0) + float(d.valor)

        # Calcula totais
        total_ativos = sum(ativos_por_categoria.values())
        total_passivos = sum(passivos_por_categoria.values())
        patrimonio_liquido = total_ativos - total_passivos

    except Exception as e:
        print(f"Erro ao processar balanço: {str(e)}")
        ativos_por_categoria = {}
        passivos_por_categoria = {}
        total_ativos = 0
        total_passivos = 0
        patrimonio_liquido = 0

    MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
             'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

    return render_template('balanco.html',
                         ativos_por_categoria=ativos_por_categoria,
                         passivos_por_categoria=passivos_por_categoria,
                         total_ativos=total_ativos,
                         total_passivos=total_passivos,
                         patrimonio_liquido=patrimonio_liquido,
                         anos=range(2024, hoje.year + 11),
                         meses=MESES,
                         mes_atual=mes,
                         ano_atual=ano)

# Função para replicar registros fixos
def replicar_registros_fixos():
    print("Iniciando replicação de registros fixos...")
    
    with app.app_context():
        hoje = datetime.now().date()
        data_limite = hoje + relativedelta(months=12)  # Replica para 12 meses à frente
        
        # Replicar receitas fixas
        receitas_fixas = Receita.query.filter_by(fixa=True).all()
        for receita in receitas_fixas:
            # Pega a data mais recente desta receita fixa
            ultima_receita = Receita.query.filter_by(
                descricao=receita.descricao,
                usuario_id=receita.usuario_id,
                fixa=True
            ).order_by(Receita.data.desc()).first()
            
            data_base = ultima_receita.data if ultima_receita else receita.data
            proximo_mes = data_base + relativedelta(months=1)
            
            # Verifica se já existe lançamento para o próximo mês
            existe = Receita.query.filter(
                Receita.descricao == receita.descricao,
                Receita.usuario_id == receita.usuario_id,
                extract('month', Receita.data) == proximo_mes.month,
                extract('year', Receita.data) == proximo_mes.year
            ).first()
            
            if not existe:
                nova_receita = Receita(
                    descricao=receita.descricao,
                    valor=receita.valor,
                    categoria_id=receita.categoria_id,
                    data=proximo_mes,
                    fixa=True,
                    usuario_id=receita.usuario_id,
                    recebido=False  # Nova receita começa como não recebida
                )
                db.session.add(nova_receita)
        
        # Replicar despesas fixas
        despesas_fixas = Despesa.query.filter_by(fixa=True).all()
        for despesa in despesas_fixas:
            # Pega a data mais recente desta despesa fixa
            ultima_despesa = Despesa.query.filter_by(
                descricao=despesa.descricao,
                usuario_id=despesa.usuario_id,
                fixa=True
            ).order_by(Despesa.data.desc()).first()
            
            data_base = ultima_despesa.data if ultima_despesa else despesa.data
            proximo_mes = data_base + relativedelta(months=1)
            
            # Verifica se já existe lançamento para o próximo mês
            existe = Despesa.query.filter(
                Despesa.descricao == despesa.descricao,
                Despesa.usuario_id == despesa.usuario_id,
                extract('month', Despesa.data) == proximo_mes.month,
                extract('year', Despesa.data) == proximo_mes.year
            ).first()
            
            if not existe:
                nova_despesa = Despesa(
                    descricao=despesa.descricao,
                    valor=despesa.valor,
                    categoria_id=despesa.categoria_id,
                    data=proximo_mes,
                    fixa=True,
                    usuario_id=despesa.usuario_id,
                    pago=False  # Nova despesa começa como não paga
                )
                db.session.add(nova_despesa)
        
        try:
            db.session.commit()
            print("Replicação concluída com sucesso!")
        except Exception as e:
            db.session.rollback()
            print(f"Erro na replicação: {str(e)}")

# Configuração da tarefa agendada para rodar todo dia à meia-noite
@scheduler.task('cron', id='replicar_fixos', hour='0', minute='0')
def tarefa_replicar_fixos():
    with app.app_context():
        try:
            replicar_registros_fixos()
            print("Tarefa de replicação executada com sucesso!")
        except Exception as e:
            print(f"Erro na tarefa de replicação: {str(e)}")

# Rota para executar a replicação manualmente (apenas admin)
@app.route('/replicar_fixos')
@admin_required
def replicar_fixos():
    try:
        replicar_registros_fixos()
        flash('Registros fixos replicados com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao replicar registros: {str(e)}', 'danger')
    return redirect(url_for('admin'))

@app.route('/dre', methods=['GET', 'POST'])
@login_required
def dre():
    usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
    hoje = date.today()
    
    # Define período
    if request.method == 'POST':
        ano = int(request.form.get('ano', hoje.year))
        mes = int(request.form.get('mes', hoje.month))
    else:
        ano_param = request.args.get('ano', '')
        mes_param = request.args.get('mes', '')
        
        ano = int(ano_param) if ano_param.strip() else hoje.year
        mes = int(mes_param) if mes_param.strip() else hoje.month

    inicio = date(ano, mes, 1)
    fim = inicio + relativedelta(months=1, days=-1)
    
    # Verifica se deve incluir reservas
    incluir_reservas = request.args.get('incluir_reservas') == 'true'
    
    try:
        # Busca receitas e despesas
        receitas = Receita.query.filter(
            Receita.usuario_id == usuario_id,
            Receita.data >= inicio,
            Receita.data <= fim
        ).all()

        despesas = Despesa.query.filter(
            Despesa.usuario_id == usuario_id,
            Despesa.data >= inicio,
            Despesa.data <= fim
        ).all()

        # Processa receitas e despesas
        receitas_por_categoria = {}
        despesas_por_categoria = {}
        
        for r in receitas:
            categoria = r.categoria.nome
            receitas_por_categoria[categoria] = receitas_por_categoria.get(categoria, 0) + float(r.valor)
        
        # Adiciona reservas apenas se o botão estiver ativado
        if incluir_reservas:
            reservas = ReservaInvestimento.query.filter_by(
                usuario_id=usuario_id,
                ativo=True
            ).all()
            
            for r in reservas:
                receitas_por_categoria['Reservas e Investimentos'] = receitas_por_categoria.get('Reservas e Investimentos', 0) + float(r.valor)
        
        for d in despesas:
            categoria = d.categoria.nome
            despesas_por_categoria[categoria] = despesas_por_categoria.get(categoria, 0) + float(d.valor)

        # Calcula totais
        total_receitas = sum(receitas_por_categoria.values())
        total_despesas = sum(despesas_por_categoria.values())
        resultado = total_receitas - total_despesas

    except Exception as e:
        print(f"Erro ao processar DRE: {str(e)}")
        receitas_por_categoria = {}
        despesas_por_categoria = {}
        total_receitas = 0
        total_despesas = 0
        resultado = 0

    return render_template('dre.html',
                         anos=range(2024, hoje.year + 11),
                         meses=MESES,
                         mes_atual=mes,
                         ano_atual=ano,
                         inicio=inicio,
                         fim=fim,
                         receitas_por_categoria=receitas_por_categoria,
                         despesas_por_categoria=despesas_por_categoria,
                         total_receitas=total_receitas,
                         total_despesas=total_despesas,
                         resultado=resultado,
                         incluir_reservas=incluir_reservas)

def replicar_registros_fixos_ate_data(data_limite):
    """Replica registros fixos até uma data específica"""
    usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
    hoje = date.today()
    
    # Replicar receitas fixas
    receitas_fixas = Receita.query.filter_by(fixa=True, usuario_id=usuario_id).all()
    for receita in receitas_fixas:
        data_atual = receita.data
        while data_atual <= data_limite:
            data_atual = data_atual + relativedelta(months=1)
            
            # Verifica se já existe registro para este mês
            existe = Receita.query.filter(
                Receita.descricao == receita.descricao,
                Receita.usuario_id == usuario_id,
                Receita.data.between(
                    date(data_atual.year, data_atual.month, 1),
                    date(data_atual.year, data_atual.month, 1) + relativedelta(months=1, days=-1)
                )
            ).first()
            
            if not existe:
                nova_receita = Receita(
                    descricao=receita.descricao,
                    valor=receita.valor,
                    categoria_id=receita.categoria_id,
                    data=date(data_atual.year, data_atual.month, receita.data.day),
                    fixa=True,
                    usuario_id=usuario_id
                )
                db.session.add(nova_receita)
    
    # Replicar despesas fixas
    despesas_fixas = Despesa.query.filter_by(fixa=True, usuario_id=usuario_id).all()
    for despesa in despesas_fixas:
        data_atual = despesa.data
        while data_atual <= data_limite:
            data_atual = data_atual + relativedelta(months=1)
            
            # Verifica se já existe registro para este mês
            existe = Despesa.query.filter(
                Despesa.descricao == despesa.descricao,
                Despesa.usuario_id == usuario_id,
                Despesa.data.between(
                    date(data_atual.year, data_atual.month, 1),
                    date(data_atual.year, data_atual.month, 1) + relativedelta(months=1, days=-1)
                )
            ).first()
            
            if not existe:
                nova_despesa = Despesa(
                    descricao=despesa.descricao,
                    valor=despesa.valor,
                    categoria_id=despesa.categoria_id,
                    data=date(data_atual.year, data_atual.month, despesa.data.day),
                    fixa=True,
                    usuario_id=usuario_id
                )
                db.session.add(nova_despesa)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao replicar registros: {str(e)}")

@app.route('/editar_despesa/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_despesa(id):
    try:
        despesa = Despesa.query.get_or_404(id)
        usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
        
        if despesa.usuario_id != usuario_id:
            app.logger.warning(f'Tentativa de acesso não autorizado à despesa {id} pelo usuário {session["usuario"]}')
            flash('Acesso negado!', 'danger')
            return redirect(url_for('despesas'))
        
        if request.method == 'POST':
            try:
                app.logger.info('DEBUG: Obtendo valores do formulário...')
                novo_valor = float(request.form.get('valor'))
                nova_descricao = request.form.get('descricao')
                nova_categoria = int(request.form.get('categoria'))
                nova_data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
                novo_fixa = 'fixa' in request.form
                novo_num_repeticoes = int(request.form.get('num_repeticoes', 12))
                atualizar_futuros = 'atualizar_futuros' in request.form
                
                app.logger.info(f'DEBUG: Valores do formulário - fixa: {novo_fixa}, num_repeticoes: {novo_num_repeticoes}, atualizar_futuros: {atualizar_futuros}')
                app.logger.info(f'DEBUG: Form data: {request.form}')
                
                # Se for despesa fixa e o usuário optou por atualizar lançamentos futuros
                if novo_fixa and atualizar_futuros:
                    # Primeiro deleta todas as despesas fixas futuras com a mesma descrição
                    despesas_futuras = Despesa.query.filter(
                        Despesa.descricao == despesa.descricao,
                        Despesa.usuario_id == usuario_id,
                        Despesa.data > despesa.data,
                        Despesa.fixa == True  # Apenas despesas fixas
                    ).all()
                    
                    for desp_futura in despesas_futuras:
                        db.session.delete(desp_futura)
                    
                    # Atualiza a despesa atual
                    despesa.descricao = nova_descricao
                    despesa.valor = novo_valor
                    despesa.categoria_id = nova_categoria
                    despesa.data = nova_data
                    despesa.fixa = novo_fixa
                    despesa.num_repeticoes = novo_num_repeticoes
                    
                    try:
                        # Primeiro salva as alterações na despesa atual
                        db.session.commit()
                        app.logger.info('DEBUG: Commit das alterações realizado com sucesso')
                        
                        # Depois replica
                        app.logger.info(f'DEBUG: Iniciando replicação para {novo_num_repeticoes} meses')
                        replicar_lancamento_fixo('despesa', despesa, usuario_id)
                        app.logger.info('DEBUG: Replicação concluída')
                    except Exception as e:
                        app.logger.error(f'DEBUG: Erro durante a replicação: {str(e)}')
                        db.session.rollback()
                        raise
                else:
                    # Se não for atualizar futuros, apenas atualiza a despesa atual
                    despesa.descricao = nova_descricao
                    despesa.valor = novo_valor
                    despesa.categoria_id = nova_categoria
                    despesa.data = nova_data
                    despesa.fixa = novo_fixa
                    despesa.num_repeticoes = novo_num_repeticoes
                    db.session.commit()
                
                app.logger.info(f'Despesa {id} atualizada com sucesso pelo usuário {session["usuario"]}')
                flash('Despesa atualizada com sucesso!', 'success')
                return redirect(url_for('despesas'))
                
            except ValueError as e:
                db.session.rollback()
                app.logger.error(f'Erro de validação ao atualizar despesa {id}: {str(e)}')
                flash('Valor inválido! Por favor, insira um número válido.', 'danger')
            except Exception as e:
                db.session.rollback()
                app.logger.error(f'Erro ao atualizar despesa {id}: {str(e)}')
                flash('Erro ao atualizar despesa!', 'danger')
        
        categorias = Categoria.query.filter_by(tipo='despesa').all()
        return render_template('editar_despesa.html', despesa=despesa, categorias=categorias)
        
    except Exception as e:
        app.logger.error(f'Erro ao acessar edição de despesa {id}: {str(e)}')
        flash('Erro ao acessar despesa!', 'danger')
        return redirect(url_for('despesas'))

@app.route('/editar_receita/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_receita(id):
    try:
        receita = Receita.query.get_or_404(id)
        usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
        
        if receita.usuario_id != usuario_id:
            app.logger.warning(f'Tentativa de acesso não autorizado à receita {id} pelo usuário {session["usuario"]}')
            flash('Acesso negado!', 'danger')
            return redirect(url_for('receitas'))
        
        if request.method == 'POST':
            try:
                app.logger.info('DEBUG: Obtendo valores do formulário...')
                novo_valor = float(request.form.get('valor'))
                nova_descricao = request.form.get('descricao')
                nova_categoria = int(request.form.get('categoria'))
                nova_data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
                novo_fixa = 'fixa' in request.form
                novo_num_repeticoes = int(request.form.get('num_repeticoes', 12))
                atualizar_futuros = 'atualizar_futuros' in request.form
                
                app.logger.info(f'DEBUG: Valores do formulário - fixa: {novo_fixa}, num_repeticoes: {novo_num_repeticoes}, atualizar_futuros: {atualizar_futuros}')
                app.logger.info(f'DEBUG: Form data: {request.form}')
                
                # Se for receita fixa e o usuário optou por atualizar lançamentos futuros
                if novo_fixa and atualizar_futuros:
                    # Primeiro deleta todas as receitas fixas futuras com a mesma descrição
                    receitas_futuras = Receita.query.filter(
                        Receita.descricao == receita.descricao,
                        Receita.usuario_id == usuario_id,
                        Receita.data > receita.data,
                        Receita.fixa == True  # Apenas receitas fixas
                    ).all()
                    
                    for rec_futura in receitas_futuras:
                        db.session.delete(rec_futura)
                    
                    # Atualiza a receita atual
                    receita.descricao = nova_descricao
                    receita.valor = novo_valor
                    receita.categoria_id = nova_categoria
                    receita.data = nova_data
                    receita.fixa = novo_fixa
                    receita.num_repeticoes = novo_num_repeticoes
                    
                    try:
                        # Primeiro salva as alterações na receita atual
                        db.session.commit()
                        app.logger.info('DEBUG: Commit das alterações realizado com sucesso')
                        
                        # Depois replica
                        app.logger.info(f'DEBUG: Iniciando replicação para {novo_num_repeticoes} meses')
                        replicar_lancamento_fixo('receita', receita, usuario_id)
                        app.logger.info('DEBUG: Replicação concluída')
                    except Exception as e:
                        app.logger.error(f'DEBUG: Erro durante a replicação: {str(e)}')
                        db.session.rollback()
                        raise
                else:
                    # Se não for atualizar futuros, apenas atualiza a receita atual
                    receita.descricao = nova_descricao
                    receita.valor = novo_valor
                    receita.categoria_id = nova_categoria
                    receita.data = nova_data
                    receita.fixa = novo_fixa
                    receita.num_repeticoes = novo_num_repeticoes
                    db.session.commit()
                
                app.logger.info(f'Receita {id} atualizada com sucesso pelo usuário {session["usuario"]}')
                flash('Receita atualizada com sucesso!', 'success')
                return redirect(url_for('receitas'))
                
            except ValueError as e:
                db.session.rollback()
                app.logger.error(f'Erro de validação ao atualizar receita {id}: {str(e)}')
                flash('Valor inválido! Por favor, insira um número válido.', 'danger')
            except Exception as e:
                db.session.rollback()
                app.logger.error(f'Erro ao atualizar receita {id}: {str(e)}')
                flash('Erro ao atualizar receita!', 'danger')
        
        categorias = Categoria.query.filter_by(tipo='receita').all()
        return render_template('editar_receita.html', receita=receita, categorias=categorias)
        
    except Exception as e:
        app.logger.error(f'Erro ao acessar edição de receita {id}: {str(e)}')
        flash('Erro ao acessar receita!', 'danger')
        return redirect(url_for('receitas'))

@app.route('/excluir_despesa/<int:id>', methods=['GET', 'POST'])
@login_required
def excluir_despesa(id):
    despesa = Despesa.query.get_or_404(id)
    
    # Verifica se a despesa pertence ao usuário logado
    if despesa.usuario_id != Usuario.query.filter_by(username=session['usuario']).first().id:
        flash('Acesso negado!', 'danger')
        return redirect(url_for('despesas'))
    
    db.session.delete(despesa)
    db.session.commit()
    flash('Despesa excluída com sucesso!', 'success')
    return redirect(url_for('despesas'))

@app.route('/excluir_receita/<int:id>', methods=['GET', 'POST'])
@login_required
def excluir_receita(id):
    try:
        receita = Receita.query.get_or_404(id)
        
        # Verifica se a receita pertence ao usuário logado
        if receita.usuario_id != Usuario.query.filter_by(username=session['usuario']).first().id:
            app.logger.warning(f'Tentativa de acesso não autorizado à receita {id} pelo usuário {session["usuario"]}')
            flash('Acesso negado!', 'danger')
            return redirect(url_for('receitas'))
        
        db.session.delete(receita)
        db.session.commit()
        app.logger.info(f'Receita {id} excluída com sucesso pelo usuário {session["usuario"]}')
        flash('Receita excluída com sucesso!', 'success')
        return redirect(url_for('receitas'))
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Erro ao excluir receita {id}: {str(e)}', exc_info=True)
        flash('Erro ao excluir receita!', 'danger')
        return redirect(url_for('receitas'))

@app.route('/limpar-despesas', methods=['POST'])  # Note o hífen no lugar do underscore
@login_required
def limpar_despesas():
    senha = request.form.get('senha_admin')
    if senha != SENHA_ADMIN:
        flash('Senha incorreta!', 'danger')
        return redirect(url_for('despesas'))
    
    try:
        usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
        Despesa.query.filter_by(usuario_id=usuario_id).delete()
        db.session.commit()
        flash('Todas as despesas foram excluídas com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir despesas: {str(e)}', 'danger')
    
    return redirect(url_for('despesas'))

@app.route('/limpar-receitas', methods=['POST'])  # Note o hífen no lugar do underscore
@login_required
def limpar_receitas():
    senha = request.form.get('senha_admin')
    if senha != SENHA_ADMIN:
        flash('Senha incorreta!', 'danger')
        return redirect(url_for('receitas'))
    
    try:
        usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
        Receita.query.filter_by(usuario_id=usuario_id).delete()
        db.session.commit()
        flash('Todas as receitas foram excluídas com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir receitas: {str(e)}', 'danger')
    
    return redirect(url_for('receitas'))

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        username = request.form.get('username')
        senha = request.form.get('senha')
        
        # Verifica se já existe um usuário com este nome
        if Usuario.query.filter_by(username=username).first():
            flash('Nome de usuário já existe!', 'danger')
            return redirect(url_for('cadastro'))
        
        # Verifica o limite de usuários
        total_usuarios = Usuario.query.count()
        app.logger.info(f'Total de usuários atual: {total_usuarios}, Limite: {LIMITE_USUARIOS}')
        
        if total_usuarios >= LIMITE_USUARIOS:
            flash(f'Limite de usuários atingido ({LIMITE_USUARIOS}). Por favor, entre em contato com o administrador em {EMAIL_CONTATO} para solicitar acesso.', 'warning')
            return redirect(url_for('login'))
        
        # Cria o novo usuário
        novo_usuario = Usuario(username=username)
        novo_usuario.set_password(senha)  # Corrigido para definir_senha
        db.session.add(novo_usuario)
        
        try:
            db.session.commit()
            app.logger.info(f'Novo usuário criado: {username}. Total após criação: {Usuario.query.count()}')
            flash('Cadastro realizado com sucesso! Faça login para continuar.', 'success')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Erro ao criar usuário: {str(e)}')
            flash('Erro ao criar usuário. Por favor, tente novamente.', 'danger')
        
        return redirect(url_for('login'))
    
    return render_template('cadastro.html')

@app.route('/marcar-despesa-paga/<int:id>')
@login_required
def marcar_despesa_paga(id):
    despesa = Despesa.query.get_or_404(id)
    if despesa.usuario_id != Usuario.query.filter_by(username=session['usuario']).first().id:
        flash('Acesso negado!', 'danger')
        return redirect(url_for('despesas'))
    
    despesa.pago = True
    db.session.commit()
    flash('Despesa marcada como paga!', 'success')
    return redirect(url_for('despesas'))

@app.route('/marcar-receita-recebida/<int:id>')
@login_required
def marcar_receita_recebida(id):
    receita = Receita.query.get_or_404(id)
    if receita.usuario_id != Usuario.query.filter_by(username=session['usuario']).first().id:
        flash('Acesso negado!', 'danger')
        return redirect(url_for('receitas'))
    
    receita.recebido = True
    db.session.commit()
    flash('Receita marcada como recebida!', 'success')
    return redirect(url_for('receitas'))

@app.route('/sobre')
@login_required
def sobre():
    return render_template('sobre.html')

@app.route('/categorias', methods=['GET', 'POST'])
@login_required
def categorias():
    try:
        if request.method == 'POST':
            nome = request.form.get('nome')
            tipo = request.form.get('tipo')
            
            if not nome or not tipo:
                flash('Nome e tipo são obrigatórios!', 'danger')
                return redirect(url_for('categorias'))
            
            nova_categoria = Categoria(nome=nome, tipo=tipo)
            db.session.add(nova_categoria)
            db.session.commit()
            app.logger.info(f'Nova categoria {nome} ({tipo}) criada pelo usuário {session["usuario"]}')
            flash('Categoria criada com sucesso!', 'success')
            return redirect(url_for('categorias'))
        
        categorias_despesa = Categoria.query.filter_by(tipo='despesa').all()
        categorias_receita = Categoria.query.filter_by(tipo='receita').all()
        
        # Se não houver categorias, cria as categorias padrão
        if not categorias_despesa and not categorias_receita:
            categorias_padrao = [
                # Categorias de Despesa
                Categoria(nome='Alimentação', tipo='despesa'),
                Categoria(nome='Moradia', tipo='despesa'),
                Categoria(nome='Transporte', tipo='despesa'),
                Categoria(nome='Saúde', tipo='despesa'),
                Categoria(nome='Educação', tipo='despesa'),
                Categoria(nome='Lazer', tipo='despesa'),
                Categoria(nome='Vestuário', tipo='despesa'),
                Categoria(nome='Contas Fixas', tipo='despesa'),
                Categoria(nome='Outros', tipo='despesa'),
                
                # Categorias de Receita
                Categoria(nome='Salário', tipo='receita'),
                Categoria(nome='Freelance', tipo='receita'),
                Categoria(nome='Investimentos', tipo='receita'),
                Categoria(nome='Vendas', tipo='receita'),
                Categoria(nome='Bônus', tipo='receita'),
                Categoria(nome='Outros', tipo='receita')
            ]
            
            for categoria in categorias_padrao:
                db.session.add(categoria)
            db.session.commit()
            
            # Atualiza as listas após criar as categorias padrão
            categorias_despesa = Categoria.query.filter_by(tipo='despesa').all()
            categorias_receita = Categoria.query.filter_by(tipo='receita').all()
        
        return render_template('categorias.html', 
                             categorias_despesa=categorias_despesa,
                             categorias_receita=categorias_receita)
        
    except Exception as e:
        app.logger.error(f'Erro ao acessar categorias: {str(e)}')
        flash('Erro ao acessar categorias!', 'danger')
        return redirect(url_for('index'))

@app.route('/editar_categoria/<int:id>', methods=['POST'])
@login_required
def editar_categoria(id):
    try:
        categoria = Categoria.query.get_or_404(id)
        novo_nome = request.form.get('nome')
        
        if not novo_nome:
            flash('Nome da categoria é obrigatório!', 'danger')
            return redirect(url_for('categorias'))
        
        # Registra o nome antigo para logging
        nome_antigo = categoria.nome
        
        # Atualiza a categoria
        categoria.nome = novo_nome
        
        # Atualiza lançamentos futuros
        data_atual = date.today()
        if categoria.tipo == 'despesa':
            # Atualiza despesas fixas futuras
            despesas_futuras = Despesa.query.filter(
                Despesa.categoria_id == id,
                Despesa.data >= data_atual,
                Despesa.fixa == True  # Apenas despesas fixas
            ).all()
            
            for despesa in despesas_futuras:
                app.logger.info(f'Atualizando categoria da despesa {despesa.id} de {nome_antigo} para {novo_nome}')
                despesa.categoria_id = id
        else:
            # Atualiza receitas fixas futuras
            receitas_futuras = Receita.query.filter(
                Receita.categoria_id == id,
                Receita.data >= data_atual,
                Receita.fixa == True  # Apenas receitas fixas
            ).all()
            
            for receita in receitas_futuras:
                app.logger.info(f'Atualizando categoria da receita {receita.id} de {nome_antigo} para {novo_nome}')
                receita.categoria_id = id
        
        db.session.commit()
        app.logger.info(f'Categoria {id} atualizada de {nome_antigo} para {novo_nome} pelo usuário {session["usuario"]}')
        flash('Categoria atualizada com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Erro ao editar categoria {id}: {str(e)}')
        flash('Erro ao editar categoria!', 'danger')
    
    return redirect(url_for('categorias'))

@app.route('/excluir_categoria/<int:id>', methods=['GET', 'POST'])
@login_required
def excluir_categoria(id):
    try:
        categoria = Categoria.query.get_or_404(id)
        
        # Verifica se existem lançamentos usando esta categoria
        if categoria.tipo == 'despesa':
            tem_lancamentos = Despesa.query.filter_by(categoria_id=id).first() is not None
        else:
            tem_lancamentos = Receita.query.filter_by(categoria_id=id).first() is not None
        
        if tem_lancamentos:
            app.logger.warning(f'Tentativa de excluir categoria {id} em uso pelo usuário {session["usuario"]}')
            flash('Não é possível excluir uma categoria que possui lançamentos!', 'danger')
            return redirect(url_for('categorias'))
        
        nome_categoria = categoria.nome
        db.session.delete(categoria)
        db.session.commit()
        app.logger.info(f'Categoria {nome_categoria} excluída com sucesso pelo usuário {session["usuario"]}')
        flash('Categoria excluída com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Erro ao excluir categoria {id}: {str(e)}')
        flash('Erro ao excluir categoria!', 'danger')
    
    return redirect(url_for('categorias'))

@app.route('/reservas', methods=['GET', 'POST'])
@login_required
def reservas():
    usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
    
    if request.method == 'POST':
        descricao = request.form.get('descricao')
        valor = request.form.get('valor')
        observacao = request.form.get('observacao')
        
        nova_reserva = ReservaInvestimento(
            descricao=descricao,
            valor=valor,
            observacao=observacao,
            usuario_id=usuario_id
        )
        
        try:
            db.session.add(nova_reserva)
            db.session.commit()
            flash('Reserva registrada com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Erro ao registrar reserva!', 'danger')
            print(str(e))
    
    # Ordena por data de atualização
    reservas = ReservaInvestimento.query.filter_by(
        usuario_id=usuario_id
    ).order_by(ReservaInvestimento.data_atualizacao.desc()).all()
    
    return render_template('reservas_investimentos.html', 
                         reservas=reservas, 
                         hoje=datetime.now())

@app.route('/toggle-receita-recebida/<int:id>', methods=['POST'])
@login_required
def toggle_receita_recebida(id):
    receita = Receita.query.get_or_404(id)
    if receita.usuario_id != Usuario.query.filter_by(username=session['usuario']).first().id:
        flash('Acesso negado!', 'danger')
        return redirect(url_for('receitas'))
    
    receita.recebido = not receita.recebido
    db.session.commit()
    flash('Status de recebimento atualizado!', 'success')
    return redirect(url_for('receitas'))

@app.route('/toggle-despesa-paga/<int:id>', methods=['POST'])
@login_required
def toggle_despesa_paga(id):
    despesa = Despesa.query.get_or_404(id)
    if despesa.usuario_id != Usuario.query.filter_by(username=session['usuario']).first().id:
        flash('Acesso negado!', 'danger')
        return redirect(url_for('despesas'))
    
    despesa.pago = not despesa.pago
    db.session.commit()
    flash('Status de pagamento atualizado!', 'success')
    return redirect(url_for('despesas'))

@app.route('/graficos', methods=['GET', 'POST'])
@login_required
def graficos():
    usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
    hoje = date.today()
    
    # Define período
    if request.method == 'POST':
        ano = int(request.form.get('ano', hoje.year))
        mes = int(request.form.get('mes', hoje.month))
    else:
        ano_param = request.args.get('ano', '')
        mes_param = request.args.get('mes', '')
        
        ano = int(ano_param) if ano_param.strip() else hoje.year
        mes = int(mes_param) if mes_param.strip() else hoje.month

    inicio = date(ano, mes, 1)
    fim = inicio + relativedelta(months=1, days=-1)
    
    try:
        dados_por_mes = []
        print("\n=== DEBUG GRÁFICOS ===")
        
        for mes_atual in range(1, 13):
            inicio_mes = date(ano, mes_atual, 1)
            fim_mes = inicio_mes + relativedelta(months=1, days=-1)
            
            # Busca todas as receitas do mês
            receitas = Receita.query.filter(
                Receita.usuario_id == usuario_id,
                Receita.data >= inicio_mes,
                Receita.data <= fim_mes
            ).all()
            
            # Debug para receitas
            print(f"\nMês {mes_atual}:")
            print("Receitas encontradas:")
            for r in receitas:
                print(f"- {r.descricao}: R${r.valor} (Fixa: {r.fixa})")
            
            # Busca todas as despesas do mês
            despesas = Despesa.query.filter(
                Despesa.usuario_id == usuario_id,
                Despesa.data >= inicio_mes,
                Despesa.data <= fim_mes
            ).all()
            
            # Debug para despesas
            print("Despesas encontradas:")
            for d in despesas:
                print(f"- {d.descricao}: R${d.valor} (Fixa: {d.fixa})")
            
            # Calcula totais
            total_receitas_mes = sum(float(r.valor) for r in receitas)
            total_despesas_mes = sum(float(d.valor) for d in despesas)
            
            print(f"Total Receitas: R${total_receitas_mes}")
            print(f"Total Despesas: R${total_despesas_mes}")
            
            # Reservas - considerando apenas as ativas até o mês atual
            reservas = ReservaInvestimento.query.filter(
                ReservaInvestimento.usuario_id == usuario_id,
                ReservaInvestimento.ativo == True,
                ReservaInvestimento.data_criacao <= fim_mes
            ).all()
            
            total_reservas_mes = sum(float(r.valor) for r in reservas)
            
            dados_por_mes.append({
                'mes': MESES[mes_atual-1],
                'receitas': total_receitas_mes,
                'despesas': total_despesas_mes,
                'reservas': total_reservas_mes
            })
        
        print("\nTotais finais:")
        print(f"Total Receitas: R${sum(d['receitas'] for d in dados_por_mes)}")
        print(f"Total Despesas: R${sum(d['despesas'] for d in dados_por_mes)}")
        print("=== FIM DEBUG ===\n")
        
        # Prepara dados para o gráfico
        meses = [d['mes'] for d in dados_por_mes]
        evolucao_receitas = [d['receitas'] for d in dados_por_mes]
        evolucao_despesas = [d['despesas'] for d in dados_por_mes]
        evolucao_reservas = [d['reservas'] for d in dados_por_mes]
        
        # Pega apenas os valores do mês selecionado (mes - 1 porque o array começa em 0)
        dados_graficos = {
            'meses': meses,
            'evolucao_receitas': evolucao_receitas,
            'evolucao_despesas': evolucao_despesas,
            'evolucao_reservas': evolucao_reservas,
            'total_receitas': evolucao_receitas[mes - 1],
            'total_despesas': evolucao_despesas[mes - 1],
            'total_reservas': evolucao_reservas[mes - 1] if evolucao_reservas else 0
        }
        
        return render_template('graficos.html',
                             anos=range(2024, hoje.year + 11),
                             meses=MESES,
                             mes_atual=mes,
                             ano_atual=ano,
                             dados_graficos=dados_graficos)
                         
    except Exception as e:
        print("Erro nos graficos:", str(e).encode('utf-8'))  # Codifica a mensagem de erro
        return render_template('graficos.html',
                             anos=range(2024, hoje.year + 11),
                             meses=MESES,
                             mes_atual=mes,
                             ano_atual=ano,
                             dados_graficos={
                                 'meses': MESES,
                                 'evolucao_receitas': [0] * 12,
                                 'evolucao_despesas': [0] * 12,
                                 'evolucao_reservas': [0] * 12,
                                 'total_receitas': 0,
                                 'total_despesas': 0,
                                 'total_reservas': 0
                             })

@app.route('/toggle_reserva_emergencia/<int:id>', methods=['POST'])
@login_required
def toggle_reserva_emergencia(id):
    try:
        reserva = ReservaInvestimento.query.get_or_404(id)
        usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
        
        if reserva.usuario_id != usuario_id:
            app.logger.warning(f'Tentativa de acesso não autorizado à reserva {id} pelo usuário {session["usuario"]}')
            flash('Acesso negado!', 'danger')
            return redirect(url_for('reservas'))
        
        reserva.ativo = not reserva.ativo
        db.session.commit()
        status = 'ativada' if reserva.ativo else 'desativada'
        app.logger.info(f'Reserva {id} {status} com sucesso pelo usuário {session["usuario"]}')
        flash(f'Reserva {status} com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Erro ao alterar status da reserva {id}: {str(e)}')
        flash('Erro ao alterar status da reserva!', 'danger')
    
    return redirect(url_for('reservas'))

@app.route('/excluir_reserva_emergencia/<int:id>', methods=['POST'])
@login_required
def excluir_reserva_emergencia(id):
    try:
        reserva = ReservaInvestimento.query.get_or_404(id)
        usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
        
        if reserva.usuario_id != usuario_id:
            app.logger.warning(f'Tentativa de acesso não autorizado para excluir reserva {id} pelo usuário {session["usuario"]}')
            flash('Acesso negado!', 'danger')
            return redirect(url_for('reservas'))
        
        db.session.delete(reserva)
        db.session.commit()
        app.logger.info(f'Reserva {id} excluída com sucesso pelo usuário {session["usuario"]}')
        flash('Reserva excluída com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Erro ao excluir reserva {id}: {str(e)}')
        flash('Erro ao excluir reserva!', 'danger')
    
    return redirect(url_for('reservas'))

@app.route('/editar_reserva_emergencia/<int:id>', methods=['POST'])
@login_required
def editar_reserva_emergencia(id):
    try:
        reserva = ReservaInvestimento.query.get_or_404(id)
        usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
        
        if reserva.usuario_id != usuario_id:
            app.logger.warning(f'Tentativa de acesso não autorizado para editar reserva {id} pelo usuário {session["usuario"]}')
            flash('Acesso negado!', 'danger')
            return redirect(url_for('reservas'))
        
        reserva.descricao = request.form.get('descricao')
        reserva.valor = float(request.form.get('valor'))
        reserva.observacao = request.form.get('observacao')
        
        db.session.commit()
        app.logger.info(f'Reserva {id} atualizada com sucesso pelo usuário {session["usuario"]}')
        flash('Reserva atualizada com sucesso!', 'success')
        
    except ValueError as e:
        db.session.rollback()
        app.logger.error(f'Erro de validação ao atualizar reserva {id}: {str(e)}')
        flash('Valor inválido! Por favor, insira um número válido.', 'danger')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Erro ao atualizar reserva {id}: {str(e)}')
        flash('Erro ao atualizar reserva!', 'danger')
    
    return redirect(url_for('reservas'))

@app.route('/editar_reserva/<int:id>', methods=['GET', 'POST'])
@login_required 
def editar_reserva(id):
    app.logger.info(f'Redirecionando rota antiga editar_reserva para editar_reserva_emergencia')
    return redirect(url_for('editar_reserva_emergencia', id=id))

@app.route('/excluir_reserva/<int:id>', methods=['POST'])
@login_required
def excluir_reserva(id):
    app.logger.info(f'Redirecionando rota antiga excluir_reserva para excluir_reserva_emergencia')
    return redirect(url_for('excluir_reserva_emergencia', id=id))

@app.route('/replicar_lancamento_fixo', methods=['POST'])
@login_required
def replicar_lancamento_fixo():
    try:
        tipo = request.form.get('tipo')  # 'receita' ou 'despesa'
        lancamento_id = request.form.get('lancamento_id')
        usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
        
        if tipo == 'receita':
            lancamento = Receita.query.get_or_404(lancamento_id)
        else:
            lancamento = Despesa.query.get_or_404(lancamento_id)
        
        if lancamento.usuario_id != usuario_id:
            app.logger.warning(f'Tentativa de acesso não autorizado para replicar {tipo} {lancamento_id}')
            flash('Acesso negado!', 'danger')
            return redirect(url_for('home'))
        
        replicar_lancamento_fixo(tipo, lancamento, usuario_id)
        
        flash(f'{tipo.capitalize()} replicada com sucesso!', 'success')
        
    except Exception as e:
        app.logger.error(f'Erro ao replicar {tipo} {lancamento_id}: {str(e)}')
        flash('Erro ao replicar lançamento!', 'danger')
    
    return redirect(url_for('home'))

def replicar_lancamento_fixo(tipo, lancamento, usuario_id):
    """
    Replica um lançamento fixo para o número de meses especificado
    tipo: 'receita' ou 'despesa'
    """
    app.logger.info(f'DEBUG: Entrando em replicar_lancamento_fixo - tipo: {tipo}, lancamento_id: {lancamento.id}, fixa: {lancamento.fixa}')
    
    if not lancamento.fixa:
        app.logger.warning('DEBUG: Tentativa de replicar lançamento não fixo')
        return
        
    data_base = lancamento.data
    num_repeticoes = getattr(lancamento, 'num_repeticoes', 12)  # Usa 12 como padrão se não encontrar o atributo
    app.logger.info(f'DEBUG: Replicando por {num_repeticoes} meses a partir de {data_base}')
    
    for i in range(1, num_repeticoes + 1):  # Replica para o número de meses especificado
        nova_data = data_base + relativedelta(months=i)
        app.logger.info(f'DEBUG: Criando lançamento para {nova_data}')
        
        try:
            if tipo == 'receita':
                # Verifica se já existe uma receita fixa para esta data
                existe = Receita.query.filter(
                    Receita.descricao == lancamento.descricao,
                    Receita.usuario_id == usuario_id,
                    Receita.data == nova_data,
                    Receita.fixa == True  # Apenas receitas fixas
                ).first()
                
                if not existe:
                    novo_lancamento = Receita(
                        descricao=lancamento.descricao,
                        valor=lancamento.valor,
                        data=nova_data,
                        categoria_id=lancamento.categoria_id,
                        usuario_id=usuario_id,
                        fixa=True,
                        num_repeticoes=num_repeticoes,
                        recebido=False
                    )
                    db.session.add(novo_lancamento)
                    app.logger.info(f'DEBUG: Nova receita criada para {nova_data}')
            else:  # despesa
                # Verifica se já existe uma despesa fixa para esta data
                existe = Despesa.query.filter(
                    Despesa.descricao == lancamento.descricao,
                    Despesa.usuario_id == usuario_id,
                    Despesa.data == nova_data,
                    Despesa.fixa == True  # Apenas despesas fixas
                ).first()
                
                if not existe:
                    novo_lancamento = Despesa(
                        descricao=lancamento.descricao,
                        valor=lancamento.valor,
                        data=nova_data,
                        categoria_id=lancamento.categoria_id,
                        usuario_id=usuario_id,
                        fixa=True,
                        num_repeticoes=num_repeticoes,
                        pago=False
                    )
                    db.session.add(novo_lancamento)
                    app.logger.info(f'DEBUG: Nova despesa criada para {nova_data}')
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"DEBUG: Erro ao replicar lançamento para {nova_data}: {str(e)}")
            raise

@app.route('/admin/usuarios', methods=['GET', 'POST'])
@admin_required
def admin_usuarios():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'
        
        # Verifica se já existe um usuário com este nome
        if Usuario.query.filter_by(username=username).first():
            flash('Nome de usuário já existe!', 'danger')
        else:
            # Verifica o limite de usuários
            total_usuarios = Usuario.query.count()
            app.logger.info(f'Total de usuários atual: {total_usuarios}, Limite: {LIMITE_USUARIOS}')
            
            if total_usuarios >= LIMITE_USUARIOS:
                flash(f'Limite de usuários atingido ({LIMITE_USUARIOS}). Não é possível criar mais usuários.', 'warning')
            else:
                try:
                    novo_usuario = Usuario(username=username, is_admin=is_admin)
                    novo_usuario.set_password(password)
                    db.session.add(novo_usuario)
                    db.session.commit()
                    flash('Usuário criado com sucesso!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Erro ao criar usuário: {str(e)}', 'danger')
                    app.logger.error(f'Erro ao criar usuário: {str(e)}')
    
    usuarios = Usuario.query.all()
    total_usuarios = len(usuarios)
    pode_criar = total_usuarios < LIMITE_USUARIOS
    
    return render_template('admin/usuarios.html', usuarios=usuarios, pode_criar=pode_criar, limite_usuarios=LIMITE_USUARIOS)

@app.route('/admin/usuarios/excluir/<int:id>', methods=['POST'])
@admin_required
def excluir_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    if usuario.username == session['usuario']:
        flash('Você não pode excluir seu próprio usuário!', 'danger')
        return redirect(url_for('admin_usuarios'))
    
    # Verifica se o usuário tem registros
    tem_despesas = Despesa.query.filter_by(usuario_id=usuario.id).count() > 0
    tem_receitas = Receita.query.filter_by(usuario_id=usuario.id).count() > 0
    tem_reservas = ReservaInvestimento.query.filter_by(usuario_id=usuario.id).count() > 0
    
    # Se não foi confirmada a exclusão e existem registros
    if not request.form.get('confirmar') and (tem_despesas or tem_receitas or tem_reservas):
        mensagem = "Este usuário possui "
        itens = []
        if tem_despesas:
            itens.append("despesas")
        if tem_receitas:
            itens.append("receitas")
        if tem_reservas:
            itens.append("reservas/investimentos")
        
        mensagem += " e ".join(itens) + " ativos. Tem certeza que deseja excluí-lo?"
        flash(mensagem, 'warning')
        return render_template('admin/confirmar_exclusao.html', usuario=usuario)
    
    try:
        # Exclui todos os registros relacionados
        ReservaInvestimento.query.filter_by(usuario_id=usuario.id).delete()
        Despesa.query.filter_by(usuario_id=usuario.id).delete()
        Receita.query.filter_by(usuario_id=usuario.id).delete()
        
        # Exclui o usuário
        db.session.delete(usuario)
        db.session.commit()
        flash('Usuário excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir usuário: {str(e)}', 'danger')
        print(f"Erro detalhado ao excluir usuário: {str(e)}")
    
    return redirect(url_for('admin_usuarios'))

@app.errorhandler(404)
def not_found_error(error):
    app.logger.error(f'Página não encontrada: {request.url}')
    return render_template('error.html',
                         error_code=404,
                         error_name='Página Não Encontrada',
                         error_description='A página que você está procurando não existe.'), 404

@app.errorhandler(405)
def method_not_allowed_error(error):
    app.logger.error(f'Método não permitido: {request.method} {request.url}')
    return render_template('error.html',
                         error_code=405,
                         error_name='Método Não Permitido',
                         error_description='O método usado não é permitido para esta URL.',
                         error_details=f'Método {request.method} não é permitido para {request.url}'), 405

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    app.logger.error('Erro do servidor: %s', error, exc_info=True)
    return render_template('error.html',
                         error_code=500,
                         error_name='Erro Interno do Servidor',
                         error_description='Ocorreu um erro interno no servidor. Nossa equipe foi notificada.'), 500

@app.route('/exportar_receitas_csv')
@login_required
def exportar_receitas_csv():
    usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
    
    # Busca todas as receitas do usuário
    receitas = Receita.query.filter_by(usuario_id=usuario_id).all()
    
    # Cria um buffer de memória para o CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Escreve o cabeçalho
    writer.writerow(['Descrição', 'Valor', 'Data', 'Categoria', 'Fixa', 'Recebido'])
    
    # Escreve os dados
    for receita in receitas:
        writer.writerow([
            receita.descricao,
            receita.valor,
            receita.data.strftime('%Y-%m-%d'),
            receita.categoria.nome,
            'Sim' if receita.fixa else 'Não',
            'Sim' if receita.recebido else 'Não'
        ])
    
    # Prepara o arquivo para download
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'receitas_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/exportar_despesas_csv')
@login_required
def exportar_despesas_csv():
    usuario_id = Usuario.query.filter_by(username=session['usuario']).first().id
    
    # Busca todas as despesas do usuário
    despesas = Despesa.query.filter_by(usuario_id=usuario_id).all()
    
    # Cria um buffer de memória para o CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Escreve o cabeçalho
    writer.writerow(['Descrição', 'Valor', 'Data', 'Categoria', 'Fixa', 'Pago'])
    
    # Escreve os dados
    for despesa in despesas:
        writer.writerow([
            despesa.descricao,
            despesa.valor,
            despesa.data.strftime('%Y-%m-%d'),
            despesa.categoria.nome,
            'Sim' if despesa.fixa else 'Não',
            'Sim' if despesa.pago else 'Não'
        ])
    
    # Prepara o arquivo para download
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'despesas_{datetime.now().strftime("%Y%m%d")}.csv'
    )

if __name__ == '__main__':
    # Inicializa o scheduler apenas uma vez
    if not scheduler.running:
        scheduler.init_app(app)
        scheduler.start()

    # Garante que o diretório instance existe
    instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)

    # Cria as tabelas e o usuário admin se não existirem
    with app.app_context():
        db.create_all()
        
        # Cria usuário admin se não existir
        if not Usuario.query.filter_by(username='admin').first():
            admin = Usuario(username='admin', is_admin=True)
            admin.set_password('admin')
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
            
            db.session.commit()

    app.run(debug=True)
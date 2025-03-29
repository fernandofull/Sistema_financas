import sqlite3

def check_database():
    try:
        # Conecta ao banco de dados
        conn = sqlite3.connect('instance/financas.db')
        cursor = conn.cursor()
        
        # Lista todas as tabelas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print("\nTabelas encontradas:")
        for table in tables:
            print(f"\n=== Tabela: {table[0]} ===")
            # Lista os registros de cada tabela
            cursor.execute(f"SELECT * FROM {table[0]}")
            records = cursor.fetchall()
            
            # Obtém os nomes das colunas
            cursor.execute(f"PRAGMA table_info({table[0]})")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            print("Colunas:", ", ".join(column_names))
            print(f"Número de registros: {len(records)}")
            
            # Mostra alguns registros de exemplo (limitado a 5)
            if records:
                print("\nPrimeiros registros (até 5):")
                for record in records[:5]:
                    print(record)
            
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Erro ao acessar o banco de dados: {e}")

if __name__ == "__main__":
    check_database()

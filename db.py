import psycopg2
from psycopg2 import Error
import pandas as pd

class Database:
    def __init__(self, host='localhost', database='attendance_db', user='postgres', password='123654789'):
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.conn = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password
            )
            return True
        except Error as e:
            print(f"Ошибка подключения: {e}")
            return False

    def close(self):
        if self.conn:
            self.conn.close()

    def execute_query(self, query, params=None, fetch=True):
        if not self.conn:
            print("Нет соединения с БД")
            return None
        
        try:
            cur = self.conn.cursor()
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            
            if fetch and query.strip().upper().startswith('SELECT'):
                result = cur.fetchall()
            else:
                result = None
            
            cur.close()
            return result
        except Error as e:
            print(f"Ошибка выполнения запроса: {e}")
            print(f"Запрос: {query}")
            if params:
                print(f"Параметры: {params}")
            return None

    def execute_insert(self, query, params=None, return_id=False):
        if not self.conn:
            print("Нет соединения с БД")
            return False
        
        try:
            cur = self.conn.cursor()
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            
            if return_id and 'RETURNING' in query.upper():
                result = cur.fetchone()[0]
            else:
                result = True
                
            self.conn.commit()
            cur.close()
            return result if return_id else True
        except Error as e:
            print(f"Ошибка вставки/обновления данных: {e}")
            self.conn.rollback()
            return False

    def get_id_by_name(self, table, column, value):
        if not self.conn:
            return None
        
        try:
            query = f"SELECT id FROM {table} WHERE {column} = %s"
            result = self.execute_query(query, (value,))
            return result[0][0] if result else None
        except Exception as e:
            print(f"Ошибка при получении ID: {e}")
            return None

    def get_user_by_login(self, login):
        query = """
        SELECT id, login, password_hash, full_name, role, group_id 
        FROM users 
        WHERE login = %s
        """
        return self.execute_query(query, (login,))
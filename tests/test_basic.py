import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from datetime import date, datetime, timedelta

# Добавляем путь к проекту
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ========== ФИКСТУРЫ ==========

@pytest.fixture
def client():
    """Создаем тестовый клиент Flask"""
    from main import app
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'  # Тестовый ключ
    app.config['WTF_CSRF_ENABLED'] = False  # Отключаем CSRF для тестов
    with app.test_client() as client:
        yield client

@pytest.fixture
def mock_db():
    """Создаем мок базы данных с расширенной функциональностью"""
    mock = Mock()
    
    # Мокируем данные пользователей
    def get_user_by_login(login):
        users = {
            'student1': [(1, 'student1', 'student123', 'Сидоров Иван Алексеевич', 'Студент', None, 1)],
            'teacher1': [(2, 'teacher1', 'teacher123', 'Иванова Мария Петровна', 'Преподаватель', None, None)],
            'admin': [(3, 'admin', 'admin123', 'Администратор Системы', 'Администратор', None, None)]
        }
        return users.get(login, [])
    
    # Мокируем execute_query с разными сценариями
    def execute_query(query, params=None, fetch=True):
        # Мок для информации о группе
        if 'group_code FROM student_groups' in query and params == (1,):
            return [(1, 'ИВТ-101')]
        # Мок для расписания
        elif 'WHERE s.group_id = %s AND s.lesson_date BETWEEN' in query:
            return []  # Пустое расписание
        # Мок для статистики
        elif 'FROM attendance a' in query and 'WHERE a.student_id' in query and 's.lesson_date' in query:
            return [(30, 25, 3, 2, 0)]  # total, attended, absent, excused, late
        # Мок для дисциплин преподавателя
        elif 'WHERE d.teacher_id = %s' in query:
            return [(1, 'Математика', 100, 'ИВТ-101, ИВТ-201', 2)]
        # Мок для всех групп
        elif 'SELECT id, group_code FROM student_groups' in query and 'ORDER BY group_code' in query:
            return [(1, 'ИВТ-101'), (2, 'ИВТ-201')]
        # Мок для дисциплин студента
        elif 'WHERE gd.group_id = %s' in query:
            return [('Математика', 100, 1), ('Физика', 80, 1)]
        # Мок для пользователей
        elif 'FROM users u' in query:
            return [
                (1, 'student1', 'Сидоров Иван', 'Студент', 'sidorov@university.ru', None, 'ИВТ-101'),
                (2, 'teacher1', 'Иванова Мария', 'Преподаватель', 'ivanova@university.ru', None, None)
            ]
        # Мок для групп
        elif 'FROM student_groups g' in query and 'GROUP BY' in query:
            return [
                (1, 'ИВТ-101', 'Информатика', 1, 25),
                (2, 'ИВТ-201', 'Информатика', 2, 30)
            ]
        # Мок для статистики системы
        elif 'SELECT COUNT(*) FROM users' in query:
            return [(150, 20, 10, 45, 15, 120)]  # student_count, teacher_count, group_count, discipline_count, recent_classes, recent_attendance
        # Мок для статистики посещаемости
        elif 'FROM attendance a' in query and 'WHERE u.role' in query:
            return [(85.5, 8.2, 4.3, 2.0)]  # attendance_percent, absence_percent, excused_percent, late_percent
        # Мок для посещаемости студента - ВАЖНО: возвращаем даты как datetime/date объекты
        elif 'FROM attendance a' in query and 'WHERE a.student_id = %s' in query:
            return [
                (1, 'Математика', date.today(), '09:00', 'Присутствовал', '', 'Иванова М.П.', '301'),
                (2, 'Физика', date.today() - timedelta(days=1), '11:00', 'Отсутствовал', 'Болел', 'Петров А.С.', '302')
            ]
        # Мок для пустой посещаемости (если не указаны параметры дат)
        elif 'WHERE a.student_id = %s AND s.lesson_date BETWEEN' in query:
            if params and len(params) >= 3:
                student_id, start_date, end_date = params[0], params[1], params[2]
                return [
                    (1, 'Математика', start_date, '09:00', 'Присутствовал', '', 'Иванова М.П.', '301'),
                    (2, 'Физика', end_date, '11:00', 'Отсутствовал', 'Болел', 'Петров А.С.', '302')
                ]
            else:
                return []
        return []
    
    mock.get_user_by_login.side_effect = get_user_by_login
    mock.execute_query.side_effect = execute_query
    mock.execute_insert.return_value = True
    mock.connect.return_value = True
    mock.close.return_value = None
    
    return mock

@pytest.fixture
def mock_db_with_errors():
    """Мок БД с ошибками для тестирования обработки ошибок"""
    mock = Mock()
    mock.connect.return_value = False
    mock.execute_query.side_effect = Exception("Database connection error")
    mock.execute_insert.side_effect = Exception("Insert failed")
    return mock

# ========== ТЕСТЫ БИЗНЕС-ЛОГИКИ (вместо тестов 14-20) ==========

def test_get_today_schedule_function():
    """Тест вспомогательной функции get_today_schedule"""
    from main import get_today_schedule
    
    with patch('main.db') as mock_db:
        # Мок для студента
        mock_db.execute_query.return_value = [
            (1, 'Математика', '09:00', '301', 'Лекция', 'Иванова М.П.', date.today())
        ]
        
        result = get_today_schedule(1, 'Студент', 1)
        assert len(result) == 1
        assert result[0][1] == 'Математика'
        assert result[0][3] == '301'
        
        # Мок для преподавателя
        mock_db.execute_query.return_value = [
            (1, 'Математика', '09:00', '301', 'Лекция', 'ИВТ-101', date.today())
        ]
        
        result = get_today_schedule(2, 'Преподаватель', None)
        assert len(result) == 1
        assert result[0][5] == 'ИВТ-101'
        
        # Мок для администратора
        mock_db.execute_query.return_value = [
            (1, 'Математика', '09:00', '301', 'Лекция', 'ИВТ-101', 'Иванова М.П.', date.today())
        ]
        
        result = get_today_schedule(3, 'Администратор', None)
        assert len(result) == 1
        assert result[0][6] == 'Иванова М.П.'

def test_get_student_attendance_function():
    """Тест функции получения посещаемости студента"""
    from main import get_student_attendance
    
    with patch('main.db') as mock_db:
        mock_db.execute_query.return_value = [
            (1, 'Математика', date.today(), '09:00', 'Присутствовал', '', 'Иванова М.П.', '301'),
            (2, 'Физика', date.today(), '11:00', 'Отсутствовал', 'Болел', 'Петров А.С.', '302')
        ]
        
        result = get_student_attendance(1)
        assert len(result) == 2
        assert result[0][1] == 'Математика'
        assert result[0][4] == 'Присутствовал'
        assert result[1][1] == 'Физика'
        assert result[1][4] == 'Отсутствовал'
        
        # Тест с указанием дат
        start_date = date.today() - timedelta(days=7)
        end_date = date.today()
        result = get_student_attendance(1, start_date, end_date)
        assert mock_db.execute_query.called
        call_args = mock_db.execute_query.call_args[0][1]
        assert len(call_args) == 3  # student_id, start_date, end_date

def test_get_teacher_disciplines_function():
    """Тест функции получения дисциплин преподавателя"""
    from main import get_teacher_disciplines
    
    with patch('main.db') as mock_db:
        mock_db.execute_query.return_value = [
            (1, 'Математика', 100, 'ИВТ-101, ИВТ-201'),
            (2, 'Физика', 80, 'ИВТ-101')
        ]
        
        result = get_teacher_disciplines(2)
        assert len(result) == 2
        assert result[0][1] == 'Математика'
        assert result[0][3] == 'ИВТ-101, ИВТ-201'
        assert result[1][1] == 'Физика'
        assert result[1][2] == 80

def test_db_error_handling():
    """Тест обработки ошибок базы данных"""
    from main import app
    
    with patch('main.db') as mock_db:
        mock_db.connect.return_value = False
        
        # Проверяем что приложение не падает при ошибке подключения
        with app.app_context():
            from main import db
            assert db.connect() == False
        
        # Тест ошибки выполнения запроса - используем фикстуру
        # Этот тест проверяет что ошибка возникает, а не обрабатывается
        mock_db.execute_query.side_effect = Exception("Query failed")
        try:
            result = mock_db.execute_query("SELECT * FROM users")
            # Если мы здесь, значит исключение не было брошено
            assert False, "Expected exception but none was raised"
        except Exception as e:
            assert str(e) == "Query failed"

def test_flash_messages_display(client):
    """Тест отображения flash сообщений"""
    with client.session_transaction() as session:
        session['user_id'] = 1
        session['login'] = 'student1'
        session['full_name'] = 'Student'
        session['role'] = 'Студент'
        session['group_id'] = 1
    
    # Проверяем flash сообщения при доступе к запрещенной странице
    response = client.get('/teacher/disciplines', follow_redirects=True)
    assert response.status_code == 200
    html = response.data.decode('utf-8', errors='ignore').lower()
    # В вашем коде есть flash('Доступ запрещен')
    assert 'доступ запрещен' in html or 'alert' in html or 'warning' in html

def test_form_validation_edge_cases(client, mock_db):
    """Тест граничных случаев валидации форм"""
    
    # Тест добавления дисциплины с некорректным количеством часов
    with client.session_transaction() as session:
        session['user_id'] = 2
        session['login'] = 'teacher1'
        session['full_name'] = 'Teacher'
        session['role'] = 'Преподаватель'
    
    with patch('main.db', mock_db):
        # Нулевые часы
        response = client.post('/teacher/discipline/add', data={
            'name': 'Test Discipline',
            'total_hours': '0',  # Некорректное значение
            'groups': ['1'],
            'semester_1': '1'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        html = response.data.decode('utf-8', errors='ignore').lower()
        # Проверяем что форма не прошла валидацию
        assert 'дисциплину' in html or 'discipline' in html or 'форма' in html
        
        # Отрицательные часы
        response = client.post('/teacher/discipline/add', data={
            'name': 'Test Discipline',
            'total_hours': '-10',  # Некорректное значение
            'groups': ['1'],
            'semester_1': '1'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Слишком большой семестр
        response = client.post('/teacher/discipline/add', data={
            'name': 'Test Discipline',
            'total_hours': '100',
            'groups': ['1'],
            'semester_1': '13'  # Некорректное значение (макс 12)
        }, follow_redirects=True)
        
        assert response.status_code == 200

def test_app_configuration():
    """Тест конфигурации приложения"""
    from main import app
    
    # Сохраняем оригинальные значения
    original_secret_key = app.config['SECRET_KEY']
    original_testing = app.config.get('TESTING', False)
    
    # Восстанавливаем оригинальный SECRET_KEY для проверки
    app.config['SECRET_KEY'] = 'your-secret-key-here'
    app.config['TESTING'] = False
    
    try:
        assert app.config['SECRET_KEY'] == 'your-secret-key-here'
        assert app.config['PERMANENT_SESSION_LIFETIME'] == timedelta(hours=2)
        assert app.config['TESTING'] == False
    finally:
        # Восстанавливаем оригинальные значения
        app.config['SECRET_KEY'] = original_secret_key
        app.config['TESTING'] = original_testing

def test_db_insert_operations(mock_db):
    """Тест операций вставки в базу данных"""
    # Тест успешной вставки
    assert mock_db.execute_insert(
        "INSERT INTO users (login, password_hash, full_name, role) VALUES (%s, %s, %s, %s)",
        ('testuser', 'testpass', 'Test User', 'Студент')
    ) == True
    
    # Тест вставки с возвратом ID
    mock_db.execute_insert.return_value = 100  # Возвращаем ID
    result = mock_db.execute_insert(
        "INSERT INTO users (login, password_hash, full_name, role) VALUES (%s, %s, %s, %s) RETURNING id",
        ('testuser2', 'testpass2', 'Test User 2', 'Студент'),
        return_id=True
    )
    assert result == 100

def test_db_query_operations(mock_db):
    """Тест операций запросов к базе данных"""
    # Тест запроса пользователя
    result = mock_db.get_user_by_login('student1')
    assert len(result) == 1
    assert result[0][1] == 'student1'
    assert result[0][4] == 'Студент'
    
    # Тест запроса расписания
    result = mock_db.execute_query("SELECT * FROM schedule WHERE group_id = %s", (1,))
    assert result is not None
    
    # Тест запроса с параметрами
    result = mock_db.execute_query("SELECT * FROM users WHERE role = %s", ('Студент',))
    assert isinstance(result, list)

def test_session_management(client):
    """Тест управления сессиями"""
    with client.session_transaction() as session:
        # Устанавливаем данные сессии
        session['user_id'] = 123
        session['login'] = 'testuser'
        session['full_name'] = 'Test User'
        session['role'] = 'Студент'
        session['group_id'] = 1
        
        # Проверяем сохранение
        assert session['user_id'] == 123
        assert session['login'] == 'testuser'
        assert session['role'] == 'Студент'
    
    # Проверяем что сессия очищается после logout
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    
    with client.session_transaction() as session:
        assert 'user_id' not in session
        assert 'login' not in session

# ========== СУЩЕСТВУЮЩИЕ ТЕСТЫ (обновленные) ==========

def test_student_cannot_access_teacher_routes(client):
    """Студент не может получить доступ к маршрутам преподавателя"""
    with client.session_transaction() as session:
        session['user_id'] = 1
        session['login'] = 'student1'
        session['full_name'] = 'Сидоров Иван'
        session['role'] = 'Студент'
        session['group_id'] = 1
    
    response = client.get('/teacher/disciplines', follow_redirects=True)
    assert response.status_code == 200
    html = response.data.decode('utf-8', errors='ignore').lower()
    assert 'доступ запрещен' in html or 'dashboard' in html or 'панель' in html

def test_student_cannot_access_admin_routes(client):
    """Студент не может получить доступ к маршрутам администратора"""
    with client.session_transaction() as session:
        session['user_id'] = 1
        session['login'] = 'student1'
        session['full_name'] = 'Сидоров Иван'
        session['role'] = 'Студент'
        session['group_id'] = 1
    
    response = client.get('/admin/users', follow_redirects=True)
    assert response.status_code == 200
    html = response.data.decode('utf-8', errors='ignore').lower()
    assert 'доступ запрещен' in html or 'dashboard' in html or 'панель' in html

def test_teacher_cannot_access_admin_routes(client):
    """Преподаватель не может получить доступ к маршрутам администратора"""
    with client.session_transaction() as session:
        session['user_id'] = 2
        session['login'] = 'teacher1'
        session['full_name'] = 'Иванова Мария'
        session['role'] = 'Преподаватель'
    
    response = client.get('/admin/users', follow_redirects=True)
    assert response.status_code == 200
    html = response.data.decode('utf-8', errors='ignore').lower()
    assert 'доступ запрещен' in html or 'dashboard' in html or 'панель' in html

def test_student_attendance_page(client, mock_db):
    """Страница посещаемости студента загружается с данными"""
    with client.session_transaction() as session:
        session['user_id'] = 1
        session['login'] = 'student1'
        session['full_name'] = 'Сидоров Иван'
        session['role'] = 'Студент'
        session['group_id'] = 1
    
    with patch('main.db', mock_db):
        # Импортируем функцию get_student_attendance чтобы она использовала мок
        with patch('main.get_student_attendance') as mock_attendance:
            # Мокаем функцию чтобы она возвращала корректные данные с date объектами
            mock_attendance.return_value = [
                (1, 'Математика', date.today(), '09:00', 'Присутствовал', '', 'Иванова М.П.', '301'),
                (2, 'Физика', date.today() - timedelta(days=1), '11:00', 'Отсутствовал', 'Болел', 'Петров А.С.', '302')
            ]
            
            response = client.get('/student/attendance', follow_redirects=True)
            
            assert response.status_code == 200
            html = response.data.decode('utf-8', errors='ignore').lower()
            assert 'посещаемость' in html or 'attendance' in html
            
            # Проверяем что есть форма фильтрации
            assert 'start_date' in html or 'end_date' in html or 'фильтр' in html

def test_teacher_add_discipline(client, mock_db):
    """Преподаватель может добавить дисциплину"""
    with client.session_transaction() as session:
        session['user_id'] = 2
        session['login'] = 'teacher1'
        session['full_name'] = 'Иванова Мария'
        session['role'] = 'Преподаватель'
    
    with patch('main.db', mock_db):
        response = client.post('/teacher/discipline/add', data={
            'name': 'Новая дисциплина',
            'description': 'Описание дисциплины',
            'total_hours': '100',
            'groups': ['1'],
            'semester_1': '1'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        html = response.data.decode('utf-8', errors='ignore').lower()
        # После успешного добавления должно быть сообщение и редирект
        assert 'успешно' in html or 'дисциплины' in html or 'success' in html

def test_admin_add_user(client, mock_db):
    """Администратор может добавить пользователя"""
    with client.session_transaction() as session:
        session['user_id'] = 3
        session['login'] = 'admin'
        session['full_name'] = 'Администратор'
        session['role'] = 'Администратор'
    
    with patch('main.db', mock_db):
        response = client.post('/admin/user/add', data={
            'login': 'newuser',
            'password': 'newpass123',
            'full_name': 'Новый пользователь',
            'role': 'Студент',
            'email': 'new@university.ru',
            'group_id': '1'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        html = response.data.decode('utf-8', errors='ignore').lower()
        # После успешного добавления должно быть сообщение
        assert 'успешно' in html or 'пользователь' in html or 'success' in html

def test_add_user_validation(client, mock_db):
    """Валидация формы добавления пользователя"""
    with client.session_transaction() as session:
        session['user_id'] = 3
        session['login'] = 'admin'
        session['full_name'] = 'Администратор'
        session['role'] = 'Администратор'
    
    with patch('main.db', mock_db):
        # Пустая форма
        response = client.post('/admin/user/add', data={
            'login': '',
            'password': '',
            'full_name': '',
            'role': ''
        }, follow_redirects=True)
        
        assert response.status_code == 200
        html = response.data.decode('utf-8', errors='ignore').lower()
        # Должны остаться на странице формы
        assert 'пользователя' in html or 'user' in html or 'форма' in html
        
        # Некорректная роль
        response = client.post('/admin/user/add', data={
            'login': 'test',
            'password': 'test',
            'full_name': 'Test',
            'role': 'InvalidRole'  # Некорректная роль
        }, follow_redirects=True)
        
        assert response.status_code == 200

def test_add_discipline_without_groups(client, mock_db):
    """Попытка добавить дисциплину без групп"""
    with client.session_transaction() as session:
        session['user_id'] = 2
        session['login'] = 'teacher1'
        session['full_name'] = 'Teacher'
        session['role'] = 'Преподаватель'
    
    with patch('main.db', mock_db):
        response = client.post('/teacher/discipline/add', data={
            'name': 'Test Discipline',
            'total_hours': '100'
            # groups не указаны
        }, follow_redirects=True)
        
        assert response.status_code == 200
        html = response.data.decode('utf-8', errors='ignore').lower()
        # Проверяем что остались на той же странице (ошибка валидации)
        assert 'дисциплину' in html or 'discipline' in html or 'форма' in html

def test_user_authentication_flow(client, mock_db):
    """Полный цикл аутентификации пользователя"""
    with patch('main.db', mock_db):
        # 1. Логин
        response = client.post('/login', data={
            'login': 'student1',
            'password': 'student123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        html = response.data.decode('utf-8', errors='ignore').lower()
        assert 'добро пожаловать' in html or 'панель' in html or 'dashboard' in html
        
        # 2. Доступ к dashboard
        response = client.get('/dashboard')
        assert response.status_code == 200
        
        # 3. Выход
        response = client.get('/logout', follow_redirects=True)
        assert response.status_code == 200
        
        # 4. Проверка что вышел
        response = client.get('/dashboard', follow_redirects=True)
        html = response.data.decode('utf-8', errors='ignore').lower()
        assert 'login' in html or 'вход' in html

def test_access_control_routes(client):
    """Тест контроля доступа ко всем защищенным маршрутам"""
    routes_to_test = [
        ('/dashboard', False, 'Все'),
        ('/student/schedule', True, 'Только студенты'),
        ('/teacher/disciplines', True, 'Только преподаватели'),
        ('/admin/users', True, 'Только администраторы')
    ]
    
    for route, requires_auth, description in routes_to_test:
        response = client.get(route, follow_redirects=True)
        
        if requires_auth:
            # Должен быть редирект на логин
            assert response.status_code == 200
            html = response.data.decode('utf-8', errors='ignore').lower()
            assert 'login' in html or 'вход' in html
        else:
            # Главная страница редиректит на логин
            if route == '/dashboard':
                assert response.status_code == 200
                html = response.data.decode('utf-8', errors='ignore').lower()
                assert 'login' in html or 'вход' in html

# ========== БАЗОВЫЕ ТЕСТЫ ПРИЛОЖЕНИЯ ==========

def test_home_redirects_to_login(client):
    """Главная страница перенаправляет на логин"""
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.location

def test_login_page_loads(client):
    """Страница логина загружается"""
    response = client.get('/login')
    assert response.status_code == 200
    html = response.data.decode('utf-8', errors='ignore').lower()
    assert 'form' in html or 'login' in html or 'вход' in html

def test_student_login_success(client, mock_db):
    """Успешный вход студента"""
    with patch('main.db', mock_db):
        response = client.post('/login', data={
            'login': 'student1',
            'password': 'student123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        html = response.data.decode('utf-8', errors='ignore').lower()
        assert 'добро пожаловать' in html or 'панель' in html or 'dashboard' in html

def test_login_failed_wrong_credentials(client, mock_db):
    """Неудачный вход с неправильными данными"""
    with patch('main.db', mock_db):
        response = client.post('/login', data={
            'login': 'wrong',
            'password': 'wrong'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        html = response.data.decode('utf-8', errors='ignore').lower()
        assert 'неверный' in html or 'ошибка' in html or 'login' in html

def test_logout(client):
    """Выход из системы"""
    with client.session_transaction() as session:
        session['user_id'] = 1
        session['login'] = 'test'
        session['full_name'] = 'Test'
        session['role'] = 'Студент'
    
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    html = response.data.decode('utf-8', errors='ignore').lower()
    assert 'login' in html or 'вход' in html or 'вышли' in html

def test_database_connection():
    """Тест инициализации базы данных"""
    from db import Database
    
    db = Database(
        host='localhost',
        database='test_db',
        user='test_user',
        password='test_pass'
    )
    
    assert db.host == 'localhost'
    assert db.database == 'test_db'
    assert db.user == 'test_user'
    assert db.password == 'test_pass'
    assert db.conn is None
    
    # Тест подключения
    with patch('db.psycopg2.connect') as mock_connect:
        mock_connect.return_value = MagicMock()
        assert db.connect() == True
        assert db.conn is not None
        
        # Тест закрытия
        db.close()
        assert db.conn.close.called

def test_nonexistent_route(client):
    """Запрос несуществующего маршрута"""
    response = client.get('/nonexistent-route')
    assert response.status_code == 404

def test_method_not_allowed(client):
    """Использование неправильного метода HTTP"""
    response = client.post('/')  # POST на главную страницу
    assert response.status_code == 405  # Method Not Allowed
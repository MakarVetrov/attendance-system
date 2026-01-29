from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from db import Database
from datetime import datetime, date, timedelta
import calendar

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

db = Database()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def get_today_schedule(user_id, user_role, group_id=None):
    """Получить расписание на сегодня"""
    today = date.today()
    
    if user_role == 'Студент':
        query = """
        SELECT s.id, d.name, s.lesson_time, s.classroom, s.lesson_type, 
               u.full_name as teacher_name, s.lesson_date
        FROM schedule s
        JOIN disciplines d ON s.discipline_id = d.id
        JOIN users u ON s.teacher_id = u.id
        WHERE s.group_id = %s AND s.lesson_date = %s
        ORDER BY s.lesson_time
        """
        result = db.execute_query(query, (group_id, today))
        # Добавляем дату к результату
        return result
    
    elif user_role == 'Преподаватель':
        query = """
        SELECT s.id, d.name, s.lesson_time, s.classroom, s.lesson_type,
               g.group_code, s.lesson_date
        FROM schedule s
        JOIN disciplines d ON s.discipline_id = d.id
        JOIN student_groups g ON s.group_id = g.id
        WHERE s.teacher_id = %s AND s.lesson_date = %s
        ORDER BY s.lesson_time
        """
        return db.execute_query(query, (user_id, today))
    
    else:  # Администратор
        query = """
        SELECT s.id, d.name, s.lesson_time, s.classroom, s.lesson_type,
               g.group_code, u.full_name as teacher_name, s.lesson_date
        FROM schedule s
        JOIN disciplines d ON s.discipline_id = d.id
        JOIN student_groups g ON s.group_id = g.id
        JOIN users u ON s.teacher_id = u.id
        WHERE s.lesson_date = %s
        ORDER BY s.lesson_time, g.group_code
        """
        return db.execute_query(query, (today,))

def get_student_attendance(student_id, start_date=None, end_date=None):
    """Получить посещаемость студента за период"""
    if not start_date:
        start_date = date.today() - timedelta(days=30)
    if not end_date:
        end_date = date.today()
    
    query = """
    SELECT a.id, d.name, s.lesson_date, s.lesson_time, a.status, a.notes,
           u.full_name as teacher_name, s.classroom
    FROM attendance a
    JOIN schedule s ON a.schedule_id = s.id
    JOIN disciplines d ON s.discipline_id = d.id
    JOIN users u ON s.teacher_id = u.id
    WHERE a.student_id = %s AND s.lesson_date BETWEEN %s AND %s
    ORDER BY s.lesson_date DESC, s.lesson_time DESC
    """
    return db.execute_query(query, (student_id, start_date, end_date))

def get_group_students(group_id):
    """Получить всех студентов группы"""
    query = """
    SELECT id, full_name, login, email
    FROM users
    WHERE role = 'Студент' AND group_id = %s
    ORDER BY full_name
    """
    return db.execute_query(query, (group_id,))

def get_teacher_disciplines(teacher_id):
    """Получить дисциплины преподавателя с названиями групп"""
    query = """
    SELECT d.id, d.name, d.total_hours,
           COALESCE(STRING_AGG(g.group_code, ', ' ORDER BY g.group_code), 'Нет групп') as group_names
    FROM disciplines d
    LEFT JOIN group_disciplines gd ON d.id = gd.discipline_id
    LEFT JOIN student_groups g ON gd.group_id = g.id
    WHERE d.teacher_id = %s
    GROUP BY d.id, d.name, d.total_hours
    ORDER BY d.name
    """
    return db.execute_query(query, (teacher_id,))

# ========== МАРШРУТЫ АУТЕНТИФИКАЦИИ ==========

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']
        
        result = db.get_user_by_login(login)
        
        if result and result[0][2] == password:  # Простая проверка пароля
            session['user_id'] = result[0][0]
            session['login'] = result[0][1]
            session['full_name'] = result[0][3]
            session['role'] = result[0][4]
            session['group_id'] = result[0][5] if result[0][5] else None
            
            flash(f'Добро пожаловать, {result[0][3]}!')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный логин или пароль')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    role = session['role']
    group_id = session.get('group_id')
    
    # Получаем расписание на сегодня
    today_schedule = get_today_schedule(user_id, role, group_id)
    today_date = date.today()
    
    if role == 'Студент':
        # Получаем дисциплины студента
        query = """
        SELECT d.name, d.total_hours, gd.semester
        FROM group_disciplines gd
        JOIN disciplines d ON gd.discipline_id = d.id
        WHERE gd.group_id = %s
        ORDER BY d.name
        """
        disciplines = db.execute_query(query, (group_id,)) if group_id else []
        
        # Получаем статистику посещаемости
        start_date = date.today() - timedelta(days=30)
        attendance_stats = db.execute_query("""
            SELECT 
                COUNT(*) as total_classes,
                SUM(CASE WHEN status = 'Присутствовал' THEN 1 ELSE 0 END) as attended,
                SUM(CASE WHEN status = 'Отсутствовал' THEN 1 ELSE 0 END) as absent,
                SUM(CASE WHEN status = 'По уважительной причине' THEN 1 ELSE 0 END) as excused,
                SUM(CASE WHEN status = 'Опоздал' THEN 1 ELSE 0 END) as late
            FROM attendance a
            JOIN schedule s ON a.schedule_id = s.id
            WHERE a.student_id = %s AND s.lesson_date BETWEEN %s AND %s
        """, (user_id, start_date, date.today()))

        stats = attendance_stats[0] if attendance_stats else (0, 0, 0, 0, 0)
        
        # Получаем название группы для отображения
        group_name = ""
        if group_id:
            group_query = "SELECT group_code FROM student_groups WHERE id = %s"
            group_info = db.execute_query(group_query, (group_id,))
            if group_info:
                group_name = group_info[0][0]
                session['group_name'] = group_name
        
        return render_template('student_dashboard.html',
                             full_name=session['full_name'],
                             role=role,
                             today_schedule=today_schedule,
                             disciplines=disciplines,
                             stats=stats,
                             today_date=today_date,
                             group_name=group_name)
    
    elif role == 'Преподаватель':
        disciplines = get_teacher_disciplines(user_id)
        
        groups_query = """
        SELECT DISTINCT g.id, g.group_code
        FROM schedule s
        JOIN student_groups g ON s.group_id = g.id
        WHERE s.teacher_id = %s
        ORDER BY g.group_code
        """
        groups = db.execute_query(groups_query, (user_id,))
        
        return render_template('teacher_dashboard.html',
                             full_name=session['full_name'],
                             role=role,
                             today_schedule=today_schedule,
                             disciplines=disciplines,
                             groups=groups,
                             today_date=today_date)
    
    else:  # Администратор
        # Статистика системы
        stats_query = """
        SELECT 
            (SELECT COUNT(*) FROM users WHERE role = 'Студент') as student_count,
            (SELECT COUNT(*) FROM users WHERE role = 'Преподаватель') as teacher_count,
            (SELECT COUNT(*) FROM student_groups) as group_count,
            (SELECT COUNT(*) FROM disciplines) as discipline_count
        """
        stats = db.execute_query(stats_query)[0] if db.execute_query(stats_query) else (0, 0, 0, 0)
        
        # Текущее время
        from datetime import datetime
        now = datetime.now()
        
        return render_template('admin_dashboard.html',
                             full_name=session['full_name'],
                             role=role,
                             today_schedule=today_schedule,
                             stats=stats,
                             today_date=today_date,
                             now=now)

# ========== МАРШРУТЫ ДЛЯ СТУДЕНТОВ ==========

@app.route('/student/schedule')
def student_schedule():
    if session.get('role') != 'Студент':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    group_id = session.get('group_id')
    if not group_id:
        flash('Вы не привязаны к группе')
        return redirect(url_for('dashboard'))
    
    # Получаем параметры даты
    week_offset = request.args.get('week_offset', 0, type=int)
    today = date.today()
    target_date = today + timedelta(weeks=week_offset)
    
    # Находим начало и конец недели
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    # Получаем информацию о группе
    group_query = "SELECT group_code FROM student_groups WHERE id = %s"
    group_info = db.execute_query(group_query, (group_id,))
    group_name = group_info[0][0] if group_info else "Неизвестная группа"
    
    # Получаем расписание на неделю
    query = """
    SELECT s.id, d.name, s.lesson_date, s.lesson_time, s.classroom, 
           s.lesson_type, u.full_name as teacher_name
    FROM schedule s
    JOIN disciplines d ON s.discipline_id = d.id
    JOIN users u ON s.teacher_id = u.id
    WHERE s.group_id = %s AND s.lesson_date BETWEEN %s AND %s
    ORDER BY s.lesson_date, s.lesson_time
    """
    
    schedule = db.execute_query(query, (group_id, start_of_week, end_of_week))
    
    # Группируем по дням
    schedule_by_day = {}
    for item in schedule:
        day = item[2]
        if day not in schedule_by_day:
            schedule_by_day[day] = []
        schedule_by_day[day].append(item)
    
    return render_template('student_schedule.html',
                         schedule_by_day=schedule_by_day,
                         start_of_week=start_of_week,
                         end_of_week=end_of_week,
                         week_offset=week_offset,
                         group_name=group_name,
                         full_name=session['full_name'],
                         today_date=today)  # Добавлено

@app.route('/student/attendance')
def student_attendance():
    if session.get('role') != 'Студент':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    # Получаем параметры фильтрации
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    attendance = get_student_attendance(session['user_id'], start_date, end_date)
    
    return render_template('student_attendance.html',
                         attendance=attendance,
                         start_date=start_date or (date.today() - timedelta(days=30)),
                         end_date=end_date or date.today())

@app.route('/student/disciplines')
def student_disciplines():
    if session.get('role') != 'Студент':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    group_id = session.get('group_id')
    if not group_id:
        flash('Вы не привязаны к группе')
        return redirect(url_for('dashboard'))
    
    query = """
    SELECT d.id, d.name, d.description, d.total_hours, gd.semester,
           u.full_name as teacher_name,
           (SELECT COUNT(*) FROM attendance a 
            JOIN schedule s ON a.schedule_id = s.id 
            WHERE s.discipline_id = d.id AND a.student_id = %s) as attended_classes
    FROM group_disciplines gd
    JOIN disciplines d ON gd.discipline_id = d.id
    JOIN users u ON d.teacher_id = u.id
    WHERE gd.group_id = %s
    ORDER BY d.name
    """
    
    disciplines = db.execute_query(query, (session['user_id'], group_id))
    
    return render_template('student_disciplines.html', disciplines=disciplines)

# ========== МАРШРУТЫ ДЛЯ ПРЕПОДАВАТЕЛЕЙ ==========

@app.route('/teacher/discipline/edit/<int:discipline_id>', methods=['GET', 'POST'])
def edit_discipline(discipline_id):
    if session.get('role') != 'Преподаватель':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    teacher_id = session['user_id']
    
    # Проверяем, принадлежит ли дисциплина преподавателю
    check_query = "SELECT id FROM disciplines WHERE id = %s AND teacher_id = %s"
    check_result = db.execute_query(check_query, (discipline_id, teacher_id))
    
    if not check_result:
        flash('Дисциплина не найдена или у вас нет прав на ее редактирование')
        return redirect(url_for('teacher_disciplines'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        total_hours = int(request.form['total_hours'])
        
        # Обновляем дисциплину
        update_query = """
        UPDATE disciplines 
        SET name = %s, description = %s, total_hours = %s
        WHERE id = %s AND teacher_id = %s
        """
        
        if db.execute_insert(update_query, (name, description, total_hours, discipline_id, teacher_id)):
            # Обновляем группы (можно добавить логику изменения групп)
            flash('Дисциплина успешно обновлена')
            return redirect(url_for('teacher_disciplines'))
    
    # GET запрос - получаем данные дисциплины
    discipline_query = """
    SELECT d.name, d.description, d.total_hours,
           STRING_AGG(g.group_code, ', ') as group_names
    FROM disciplines d
    LEFT JOIN group_disciplines gd ON d.id = gd.discipline_id
    LEFT JOIN student_groups g ON gd.group_id = g.id
    WHERE d.id = %s AND d.teacher_id = %s
    GROUP BY d.id, d.name, d.description, d.total_hours
    """
    
    discipline_data = db.execute_query(discipline_query, (discipline_id, teacher_id))
    
    if not discipline_data:
        flash('Дисциплина не найдена')
        return redirect(url_for('teacher_disciplines'))
    
    # Получаем все группы для выбора
    groups_query = "SELECT id, group_code FROM student_groups ORDER BY group_code"
    groups = db.execute_query(groups_query)
    
    return render_template('edit_discipline.html',
                         discipline=discipline_data[0],
                         discipline_id=discipline_id,
                         groups=groups)

# ========== ДОПОЛНИТЕЛЬНЫЕ МАРШРУТЫ ДЛЯ ПРЕПОДАВАТЕЛЕЙ ==========

@app.route('/teacher/discipline/delete/<int:discipline_id>', methods=['POST'])
def delete_discipline(discipline_id):
    if session.get('role') != 'Преподаватель':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('dashboard'))
    
    teacher_id = session['user_id']
    
    # Проверяем, принадлежит ли дисциплина преподавателю
    check_query = "SELECT id, name FROM disciplines WHERE id = %s AND teacher_id = %s"
    check_result = db.execute_query(check_query, (discipline_id, teacher_id))
    
    if not check_result:
        flash('Дисциплина не найдена или у вас нет прав на ее удаление', 'danger')
        return redirect(url_for('teacher_disciplines'))
    
    discipline_name = check_result[0][1]
    
    # Удаляем дисциплину (cascade удалит связанные записи)
    delete_query = "DELETE FROM disciplines WHERE id = %s AND teacher_id = %s"
    
    if db.execute_insert(delete_query, (discipline_id, teacher_id)):
        flash(f'Дисциплина "{discipline_name}" успешно удалена', 'success')
    else:
        flash('Ошибка при удалении дисциплины', 'danger')
    
    return redirect(url_for('teacher_disciplines'))

@app.route('/teacher/discipline/manage_groups/<int:discipline_id>', methods=['GET', 'POST'])
def manage_discipline_groups(discipline_id):
    if session.get('role') != 'Преподаватель':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('dashboard'))
    
    teacher_id = session['user_id']
    
    # Проверяем, принадлежит ли дисциплина преподавателю
    check_query = """
    SELECT d.id, d.name 
    FROM disciplines d
    WHERE d.id = %s AND d.teacher_id = %s
    """
    check_result = db.execute_query(check_query, (discipline_id, teacher_id))
    
    if not check_result:
        flash('Дисциплина не найдена или у вас нет прав на ее редактирование', 'danger')
        return redirect(url_for('teacher_disciplines'))
    
    discipline_name = check_result[0][1]
    
    if request.method == 'POST':
        # Получаем выбранные группы из формы
        selected_groups = request.form.getlist('groups')
        
        # Удаляем все текущие связи дисциплины с группами
        delete_query = "DELETE FROM group_disciplines WHERE discipline_id = %s"
        db.execute_insert(delete_query, (discipline_id,))
        
        # Добавляем новые связи
        success = True
        for group_id in selected_groups:
            semester = request.form.get(f'semester_{group_id}', 1)
            if not db.execute_insert(
                "INSERT INTO group_disciplines (group_id, discipline_id, semester) VALUES (%s, %s, %s)",
                (group_id, discipline_id, semester)
            ):
                success = False
        
        if success:
            flash(f'Группы для дисциплины "{discipline_name}" успешно обновлены', 'success')
            return redirect(url_for('teacher_disciplines'))
        else:
            flash('Ошибка при обновлении групп', 'danger')
    
    # GET запрос - получаем данные
    # Получаем информацию о дисциплине
    discipline_query = "SELECT name, description, total_hours FROM disciplines WHERE id = %s"
    discipline_data = db.execute_query(discipline_query, (discipline_id,))[0]
    
    # Получаем все группы
    groups_query = "SELECT id, group_code FROM student_groups ORDER BY group_code"
    all_groups = db.execute_query(groups_query)
    
    # Получаем текущие группы дисциплины
    current_groups_query = """
    SELECT gd.group_id, g.group_code, gd.semester
    FROM group_disciplines gd
    JOIN student_groups g ON gd.group_id = g.id
    WHERE gd.discipline_id = %s
    ORDER BY g.group_code
    """
    current_groups = db.execute_query(current_groups_query, (discipline_id,))
    
    # Создаем словарь для быстрого доступа к семестрам текущих групп
    current_groups_dict = {str(group[0]): group[2] for group in current_groups}
    
    return render_template('manage_discipline_groups.html',
                         discipline_id=discipline_id,
                         discipline_name=discipline_name,
                         discipline_data=discipline_data,
                         all_groups=all_groups,
                         current_groups_dict=current_groups_dict)

# Обновим функцию teacher_disciplines чтобы она показывала больше информации
@app.route('/teacher/disciplines')
def teacher_disciplines():
    if session.get('role') != 'Преподаватель':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    # Получаем дисциплины с количеством групп
    disciplines_query = """
    SELECT d.id, d.name, d.total_hours,
           COALESCE(STRING_AGG(g.group_code, ', ' ORDER BY g.group_code), 'Нет групп') as group_names,
           COUNT(DISTINCT gd.group_id) as group_count
    FROM disciplines d
    LEFT JOIN group_disciplines gd ON d.id = gd.discipline_id
    LEFT JOIN student_groups g ON gd.group_id = g.id
    WHERE d.teacher_id = %s
    GROUP BY d.id, d.name, d.total_hours
    ORDER BY d.name
    """
    
    disciplines = db.execute_query(disciplines_query, (session['user_id'],))
    
    return render_template('teacher_disciplines.html', disciplines=disciplines)

@app.route('/teacher/discipline/add', methods=['GET', 'POST'])
def add_discipline():
    if session.get('role') != 'Преподаватель':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        total_hours = int(request.form['total_hours'])
        teacher_id = session['user_id']
        
        # Проверяем, выбраны ли группы (хотя бы одна)
        groups = request.form.getlist('groups')
        if not groups:
            flash('Необходимо выбрать хотя бы одну группу', 'danger')
            return redirect(url_for('add_discipline'))
        
        # Проверяем семестры для выбранных групп
        group_semesters = {}
        for group_id in groups:
            semester = request.form.get(f'semester_{group_id}')
            if not semester:
                flash(f'Для выбранной группы необходимо указать семестр', 'danger')
                return redirect(url_for('add_discipline'))
            
            try:
                semester_int = int(semester)
                if semester_int < 1 or semester_int > 12:
                    flash(f'Семестр должен быть от 1 до 12', 'danger')
                    return redirect(url_for('add_discipline'))
                group_semesters[group_id] = semester_int
            except ValueError:
                flash(f'Некорректное значение семестра', 'danger')
                return redirect(url_for('add_discipline'))
        
        # Создаем дисциплину
        query = """
        INSERT INTO disciplines (name, description, total_hours, teacher_id)
        VALUES (%s, %s, %s, %s) RETURNING id
        """
        
        discipline_id = db.execute_insert(query, (name, description, total_hours, teacher_id), return_id=True)
        
        if discipline_id:
            # Добавляем группы к дисциплине
            success = True
            for group_id, semester in group_semesters.items():
                if not db.execute_insert(
                    "INSERT INTO group_disciplines (group_id, discipline_id, semester) VALUES (%s, %s, %s)",
                    (group_id, discipline_id, semester)
                ):
                    success = False
            
            if success:
                flash(f'Дисциплина "{name}" успешно добавлена для {len(groups)} группы(рупп)', 'success')
                return redirect(url_for('teacher_disciplines'))
            else:
                flash('Ошибка при добавлении групп к дисциплине', 'danger')
        else:
            flash('Ошибка при создании дисциплины', 'danger')
    
    # GET запрос - показываем форму
    groups_query = "SELECT id, group_code FROM student_groups ORDER BY group_code"
    groups = db.execute_query(groups_query)
    
    return render_template('add_discipline.html', groups=groups)

@app.route('/teacher/attendance/mark', methods=['GET', 'POST'])
def mark_attendance():
    if session.get('role') != 'Преподаватель':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    teacher_id = session['user_id']
    
    if request.method == 'POST':
        schedule_id = request.form['schedule_id']
        student_id = request.form['student_id']
        status = request.form['status']
        notes = request.form.get('notes', '')
        
        # Проверяем, существует ли уже запись о посещаемости
        check_query = "SELECT id FROM attendance WHERE student_id = %s AND schedule_id = %s"
        existing = db.execute_query(check_query, (student_id, schedule_id))
        
        if existing:
            # Обновляем существующую запись
            update_query = """
            UPDATE attendance 
            SET status = %s, notes = %s, marked_by = %s, marked_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            db.execute_insert(update_query, (status, notes, teacher_id, existing[0][0]))
        else:
            # Создаем новую запись
            insert_query = """
            INSERT INTO attendance (student_id, schedule_id, status, notes, marked_by)
            VALUES (%s, %s, %s, %s, %s)
            """
            db.execute_insert(insert_query, (student_id, schedule_id, status, notes, teacher_id))
        
        # Возвращаем успешный ответ для AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True})
        
        flash('Посещаемость отмечена')
        return redirect(url_for('mark_attendance'))
    
    # GET запрос - показываем форму
    today = date.today()
    query = """
    SELECT s.id, d.name, s.lesson_time, g.group_code, s.classroom, s.lesson_type
    FROM schedule s
    JOIN disciplines d ON s.discipline_id = d.id
    JOIN student_groups g ON s.group_id = g.id
    WHERE s.teacher_id = %s AND s.lesson_date = %s
    ORDER BY s.lesson_time
    """
    
    today_classes = db.execute_query(query, (teacher_id, today))
    
    return render_template('mark_attendance.html', 
                         today_classes=today_classes,
                         today=today)

@app.route('/teacher/attendance/class/<int:schedule_id>')
def attendance_class(schedule_id):
    if session.get('role') != 'Преподаватель':
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    # Получаем информацию о занятии
    class_query = """
    SELECT s.id, d.name, s.lesson_date, s.lesson_time, g.group_code, 
           s.classroom, s.lesson_type, g.id as group_id
    FROM schedule s
    JOIN disciplines d ON s.discipline_id = d.id
    JOIN student_groups g ON s.group_id = g.id
    WHERE s.id = %s AND s.teacher_id = %s
    """
    
    class_info = db.execute_query(class_query, (schedule_id, session['user_id']))
    if not class_info:
        return jsonify({'error': 'Занятие не найдено'}), 404
    
    # Получаем студентов группы
    group_id = class_info[0][7]  # group_id из запроса
    students_query = """
    SELECT id, full_name, login, email
    FROM users
    WHERE role = 'Студент' AND group_id = %s
    ORDER BY full_name
    """
    students = db.execute_query(students_query, (group_id,))
    
    # Получаем текущую посещаемость
    attendance_query = """
    SELECT student_id, status, notes
    FROM attendance
    WHERE schedule_id = %s
    """
    attendance_data = db.execute_query(attendance_query, (schedule_id,))
    attendance_dict = {row[0]: {'status': row[1], 'notes': row[2]} for row in attendance_data}
    
    return jsonify({
        'class_info': {
            'id': class_info[0][0],
            'name': class_info[0][1],
            'date': class_info[0][2].strftime('%d.%m.%Y'),
            'time': str(class_info[0][3]),
            'group': class_info[0][4],
            'classroom': class_info[0][5],
            'type': class_info[0][6]
        },
        'students': [
            {
                'id': s[0],
                'name': s[1],
                'login': s[2],
                'email': s[3],
                'status': attendance_dict.get(s[0], {}).get('status', 'Не отмечен'),
                'notes': attendance_dict.get(s[0], {}).get('notes', '')
            }
            for s in students
        ]
    })

@app.route('/teacher/statistics')
def teacher_statistics():
    if session.get('role') != 'Преподаватель':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    teacher_id = session['user_id']
    
    # Получаем параметры
    group_id = request.args.get('group_id')
    student_id = request.args.get('student_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start_date = date.today() - timedelta(days=30)
    
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        end_date = date.today()
    
    # Получаем группы преподавателя
    groups_query = """
    SELECT DISTINCT g.id, g.group_code
    FROM schedule s
    JOIN student_groups g ON s.group_id = g.id
    WHERE s.teacher_id = %s
    ORDER BY g.group_code
    """
    groups = db.execute_query(groups_query, (teacher_id,))
    
    # Получаем студентов выбранной группы
    students = []
    if group_id:
        students_query = """
        SELECT u.id, u.full_name
        FROM users u
        WHERE u.role = 'Студент' AND u.group_id = %s
        ORDER BY u.full_name
        """
        students = db.execute_query(students_query, (group_id,))
    
    statistics = None
    if group_id or student_id:
        # Строим запрос для статистики - ТОЛЬКО ДЛЯ СТУДЕНТОВ
        query = """
        SELECT 
            u.full_name,
            d.name as discipline,
            COUNT(*) as total_classes,
            SUM(CASE WHEN a.status = 'Присутствовал' THEN 1 ELSE 0 END) as attended,
            SUM(CASE WHEN a.status = 'Отсутствовал' THEN 1 ELSE 0 END) as absent,
            SUM(CASE WHEN a.status = 'По уважительной причине' THEN 1 ELSE 0 END) as excused,
            SUM(CASE WHEN a.status = 'Опоздал' THEN 1 ELSE 0 END) as late
        FROM attendance a
        JOIN schedule s ON a.schedule_id = s.id
        JOIN disciplines d ON s.discipline_id = d.id
        JOIN users u ON a.student_id = u.id
        WHERE s.teacher_id = %s 
          AND u.role = 'Студент'  -- Добавлено: только студенты
          AND s.lesson_date BETWEEN %s AND %s
        """
        
        params = [teacher_id, start_date, end_date]
        
        if student_id:
            query += " AND a.student_id = %s"
            params.append(student_id)
            query += " GROUP BY u.full_name, d.name"
        elif group_id:
            query += " AND s.group_id = %s"
            params.append(group_id)
            query += " GROUP BY u.full_name, d.name"
        
        statistics = db.execute_query(query, params)
    
    return render_template('teacher_statistics.html',
                         groups=groups,
                         students=students,
                         statistics=statistics,
                         start_date=start_date,
                         end_date=end_date,
                         selected_group=group_id,
                         selected_student=student_id)

# ========== МАРШРУТЫ ДЛЯ АДМИНИСТРАТОРА ==========

@app.route('/admin/users')
def admin_users():
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    role_filter = request.args.get('role', '')
    group_filter = request.args.get('group_id', '')
    search_query = request.args.get('search', '')
    
    query = """
    SELECT u.id, u.login, u.full_name, u.role, u.email, u.phone, 
           g.group_code
    FROM users u
    LEFT JOIN student_groups g ON u.group_id = g.id
    WHERE 1=1
    """
    
    params = []
    
    if role_filter:
        query += " AND u.role = %s"
        params.append(role_filter)
    
    if group_filter:
        query += " AND u.group_id = %s"
        params.append(group_filter)
    
    if search_query:
        query += " AND u.full_name ILIKE %s"
        params.append(f"%{search_query}%")
    
    query += " ORDER BY u.role, u.full_name"
    users = db.execute_query(query, params) if params else db.execute_query(query)
    
    # Получаем список групп для фильтра
    groups_query = "SELECT id, group_code FROM student_groups ORDER BY group_code"
    all_groups = db.execute_query(groups_query)

    now = datetime.now()
    current_time = now.strftime('%H:%M')
    
    return render_template('admin_users.html', 
                         users=users, 
                         role_filter=role_filter,
                         group_filter=group_filter,
                         search_query=search_query,
                         current_time=current_time,
                         all_groups=all_groups)

@app.route('/admin/user/add', methods=['GET', 'POST'])
def add_user():
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']
        full_name = request.form['full_name']
        role = request.form['role']
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        group_id = request.form.get('group_id') if role == 'Студент' else None
        
        # Проверяем, существует ли пользователь с таким логином
        check_query = "SELECT id FROM users WHERE login = %s"
        existing = db.execute_query(check_query, (login,))
        
        if existing:
            flash('Пользователь с таким логином уже существует')
            return redirect(url_for('add_user'))
        
        query = """
        INSERT INTO users (login, password_hash, full_name, role, email, phone, group_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        if db.execute_insert(query, (login, password, full_name, role, email, phone, group_id)):
            flash('Пользователь успешно добавлен')
            return redirect(url_for('admin_users'))
    
    # GET запрос - показываем форму
    groups_query = "SELECT id, group_code FROM student_groups ORDER BY group_code"
    groups = db.execute_query(groups_query)
    
    return render_template('add_user.html', groups=groups)

@app.route('/admin/user/edit/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        login = request.form['login']
        full_name = request.form['full_name']
        role = request.form['role']
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        group_id = request.form.get('group_id') if role == 'Студент' else None
        
        query = """
        UPDATE users 
        SET login = %s, full_name = %s, role = %s, email = %s, phone = %s, group_id = %s
        WHERE id = %s
        """
        
        if db.execute_insert(query, (login, full_name, role, email, phone, group_id, user_id)):
            flash('Пользователь успешно обновлен')
            return redirect(url_for('admin_users'))
    
    # GET запрос - получаем данные пользователя
    user_query = "SELECT login, full_name, role, email, phone, group_id FROM users WHERE id = %s"
    user_data = db.execute_query(user_query, (user_id,))
    
    if not user_data:
        flash('Пользователь не найден')
        return redirect(url_for('admin_users'))
    
    groups_query = "SELECT id, group_code FROM student_groups ORDER BY group_code"
    groups = db.execute_query(groups_query)
    
    return render_template('edit_user.html', 
                         user=user_data[0], 
                         user_id=user_id, 
                         groups=groups)

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    # Нельзя удалить самого себя
    if user_id == session['user_id']:
        flash('Нельзя удалить собственный аккаунт')
        return redirect(url_for('admin_users'))
    
    delete_query = "DELETE FROM users WHERE id = %s"
    if db.execute_insert(delete_query, (user_id,)):
        flash('Пользователь удален')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/groups')
def admin_groups():
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    groups_query = """
    SELECT g.id, g.group_code, g.specialization, g.year_of_study,
           COUNT(DISTINCT u.id) as student_count
    FROM student_groups g
    LEFT JOIN users u ON g.id = u.group_id AND u.role = 'Студент'
    GROUP BY g.id, g.group_code, g.specialization, g.year_of_study
    ORDER BY g.group_code
    """
    
    groups = db.execute_query(groups_query)
    
    now = datetime.now()
    current_time = now.strftime('%H:%M')

    return render_template('admin_groups.html',
                           groups=groups,
                           current_time=current_time)

@app.route('/admin/schedule')
def admin_schedule():
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    # Получаем параметры фильтрации
    group_id = request.args.get('group_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date:
        start_date = date.today()
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        end_date = start_date + timedelta(days=6)
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Получаем все группы
    groups_query = "SELECT id, group_code FROM student_groups ORDER BY group_code"
    groups = db.execute_query(groups_query)
    
    # Получаем расписание
    query = """
    SELECT s.id, d.name, s.lesson_date, s.lesson_time, s.classroom, 
           s.lesson_type, g.group_code, u.full_name as teacher_name
    FROM schedule s
    JOIN disciplines d ON s.discipline_id = d.id
    JOIN student_groups g ON s.group_id = g.id
    JOIN users u ON s.teacher_id = u.id
    WHERE s.lesson_date BETWEEN %s AND %s
    """
    
    params = [start_date, end_date]
    
    if group_id:
        query += " AND s.group_id = %s"
        params.append(group_id)
    
    query += " ORDER BY s.lesson_date, s.lesson_time, g.group_code"
    
    schedule = db.execute_query(query, params) if params else db.execute_query(query)
    
    # Группируем по дням
    schedule_by_day = {}
    for item in schedule:
        day = item[2]
        if day not in schedule_by_day:
            schedule_by_day[day] = []
        schedule_by_day[day].append(item)
    
    now = datetime.now()
    current_time = now.strftime('%H:%M')

    return render_template('admin_schedule.html',
                         schedule_by_day=schedule_by_day,
                         groups=groups,
                         start_date=start_date,
                         end_date=end_date,
                         current_time=current_time,
                         selected_group=group_id)

@app.route('/admin/schedule/add', methods=['GET', 'POST'])
def add_schedule():
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        discipline_id = request.form['discipline_id']
        group_id = request.form['group_id']
        teacher_id = request.form['teacher_id']
        lesson_date = request.form['lesson_date']
        lesson_time = request.form['lesson_time']
        classroom = request.form.get('classroom', '')
        lesson_type = request.form['lesson_type']
        
        # Проверяем, нет ли уже занятия в это время
        check_query = """
        SELECT id FROM schedule 
        WHERE group_id = %s AND lesson_date = %s AND lesson_time = %s
        """
        existing = db.execute_query(check_query, (group_id, lesson_date, lesson_time))
        
        if existing:
            flash('В это время у группы уже есть занятие')
            return redirect(url_for('add_schedule'))
        
        query = """
        INSERT INTO schedule (discipline_id, group_id, teacher_id, lesson_date, 
                             lesson_time, classroom, lesson_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        if db.execute_insert(query, (discipline_id, group_id, teacher_id, lesson_date,
                                   lesson_time, classroom, lesson_type)):
            flash('Занятие добавлено в расписание')
            return redirect(url_for('admin_schedule'))
    
    # GET запрос - получаем данные для формы
    disciplines_query = "SELECT id, name FROM disciplines ORDER BY name"
    disciplines = db.execute_query(disciplines_query)
    
    groups_query = "SELECT id, group_code FROM student_groups ORDER BY group_code"
    groups = db.execute_query(groups_query)
    
    teachers_query = "SELECT id, full_name FROM users WHERE role = 'Преподаватель' ORDER BY full_name"
    teachers = db.execute_query(teachers_query)
    
    return render_template('add_schedule.html',
                         disciplines=disciplines,
                         groups=groups,
                         teachers=teachers)

@app.route('/admin/group/<int:group_id>/disciplines')
def group_disciplines(group_id):
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    # Получаем информацию о группе
    group_query = "SELECT group_code FROM student_groups WHERE id = %s"
    group_info = db.execute_query(group_query, (group_id,))
    if not group_info:
        flash('Группа не найдена')
        return redirect(url_for('admin_groups'))
    
    group_name = group_info[0][0]
    
    # Получаем дисциплины группы
    query = """
    SELECT d.id, d.name, d.description, d.total_hours, 
           u.full_name as teacher_name, gd.semester
    FROM group_disciplines gd
    JOIN disciplines d ON gd.discipline_id = d.id
    JOIN users u ON d.teacher_id = u.id
    WHERE gd.group_id = %s
    ORDER BY gd.semester, d.name
    """
    
    disciplines = db.execute_query(query, (group_id,))
    
    return render_template('group_disciplines.html',
                         disciplines=disciplines,
                         group_name=group_name,
                         group_id=group_id)

@app.route('/admin/statistics')
def admin_statistics():
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    # Получаем общую статистику
    stats_query = """
    SELECT 
        (SELECT COUNT(*) FROM users WHERE role = 'Студент') as student_count,
        (SELECT COUNT(*) FROM users WHERE role = 'Преподаватель') as teacher_count,
        (SELECT COUNT(*) FROM student_groups) as group_count,
        (SELECT COUNT(*) FROM disciplines) as discipline_count,
        (SELECT COUNT(*) FROM schedule WHERE lesson_date >= CURRENT_DATE - INTERVAL '7 days') as recent_classes,
        (SELECT COUNT(DISTINCT student_id) FROM attendance WHERE marked_at >= CURRENT_DATE - INTERVAL '7 days') as recent_attendance
    """
    stats = db.execute_query(stats_query)[0] if db.execute_query(stats_query) else (0, 0, 0, 0, 0, 0)
    
    # Статистика по посещаемости (ТОЛЬКО СТУДЕНТЫ)
    attendance_stats_query = """
    SELECT 
        ROUND(COUNT(CASE WHEN status = 'Присутствовал' THEN 1 END) * 100.0 / COUNT(*), 1) as attendance_percent,
        ROUND(COUNT(CASE WHEN status = 'Отсутствовал' THEN 1 END) * 100.0 / COUNT(*), 1) as absence_percent,
        ROUND(COUNT(CASE WHEN status = 'По уважительной причине' THEN 1 END) * 100.0 / COUNT(*), 1) as excused_percent,
        ROUND(COUNT(CASE WHEN status = 'Опоздал' THEN 1 END) * 100.0 / COUNT(*), 1) as late_percent
    FROM attendance a
    JOIN users u ON a.student_id = u.id
    WHERE u.role = 'Студент' AND a.marked_at >= CURRENT_DATE - INTERVAL '30 days'
    """
    attendance_stats = db.execute_query(attendance_stats_query)[0] if db.execute_query(attendance_stats_query) else (0, 0, 0, 0)
    
    # Топ групп по посещаемости (ТОЛЬКО СТУДЕНТЫ)
    top_groups_query = """
    SELECT g.group_code, 
           COUNT(*) as total_classes,
           ROUND(COUNT(CASE WHEN a.status = 'Присутствовал' THEN 1 END) * 100.0 / COUNT(*), 1) as attendance_rate
    FROM attendance a
    JOIN schedule s ON a.schedule_id = s.id
    JOIN student_groups g ON s.group_id = g.id
    JOIN users u ON a.student_id = u.id
    WHERE u.role = 'Студент' AND a.marked_at >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY g.id, g.group_code
    ORDER BY attendance_rate DESC
    LIMIT 5
    """
    top_groups = db.execute_query(top_groups_query) or []
    
    # Последние отметки посещаемости (ТОЛЬКО СТУДЕНТЫ)
    recent_attendance_query = """
    SELECT a.id, u.full_name, d.name, a.status, a.marked_at, g.group_code
    FROM attendance a
    JOIN users u ON a.student_id = u.id
    JOIN schedule s ON a.schedule_id = s.id
    JOIN disciplines d ON s.discipline_id = d.id
    JOIN student_groups g ON s.group_id = g.id
    WHERE u.role = 'Студент'
    ORDER BY a.marked_at DESC
    LIMIT 10
    """
    recent_attendance = db.execute_query(recent_attendance_query) or []
    
    now = datetime.now()
    current_time = now.strftime('%H:%M')

    return render_template('admin_statistics.html',
                         stats=stats,
                         attendance_stats=attendance_stats,
                         top_groups=top_groups,
                         recent_attendance=recent_attendance,
                         current_time = current_time)

# Добавление группы
@app.route('/admin/group/add', methods=['GET', 'POST'])
def add_group():
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        group_code = request.form['group_code']
        specialization = request.form.get('specialization', '')
        year_of_study = int(request.form['year_of_study'])
        
        # Проверяем, существует ли группа с таким кодом
        check_query = "SELECT id FROM student_groups WHERE group_code = %s"
        existing = db.execute_query(check_query, (group_code,))
        
        if existing:
            flash('Группа с таким кодом уже существует')
            return redirect(url_for('add_group'))
        
        query = """
        INSERT INTO student_groups (group_code, specialization, year_of_study)
        VALUES (%s, %s, %s)
        """
        
        if db.execute_insert(query, (group_code, specialization, year_of_study)):
            flash('Группа успешно создана')
            return redirect(url_for('admin_groups'))
    
    return render_template('add_group.html')

# Редактирование группы
@app.route('/admin/group/edit/<int:group_id>')
def edit_group(group_id):
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    # Получаем информацию о группе
    group_query = """
    SELECT id, group_code, specialization, year_of_study
    FROM student_groups 
    WHERE id = %s
    """
    group_data = db.execute_query(group_query, (group_id,))
    
    if not group_data:
        flash('Группа не найдена')
        return redirect(url_for('admin_groups'))
    
    return render_template('edit_group.html',
                         group=group_data[0])
# Обновление группы
@app.route('/admin/group/update/<int:group_id>', methods=['POST'])
def update_group(group_id):
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    group_code = request.form['group_code']
    specialization = request.form.get('specialization', '')
    year_of_study = int(request.form['year_of_study'])
    
    # Проверяем, не занят ли код группы другим группой
    check_query = "SELECT id FROM student_groups WHERE group_code = %s AND id != %s"
    existing = db.execute_query(check_query, (group_code, group_id))
    
    if existing:
        flash('Группа с таким кодом уже существует')
        return redirect(url_for('edit_group', group_id=group_id))
    
    update_query = """
    UPDATE student_groups 
    SET group_code = %s, specialization = %s, year_of_study = %s
    WHERE id = %s
    """
    
    if db.execute_insert(update_query, (group_code, specialization, year_of_study, group_id)):
        flash('Группа успешно обновлена')
    
    return redirect(url_for('edit_group', group_id=group_id))

# Удаление группы
@app.route('/admin/group/delete/<int:group_id>', methods=['POST'])
def delete_group(group_id):
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    # Удаляем группу (сработает CASCADE для студентов)
    delete_query = "DELETE FROM student_groups WHERE id = %s"
    
    if db.execute_insert(delete_query, (group_id,)):
        flash('Группа удалена')
    
    return redirect(url_for('admin_groups'))

# Добавление студента в группу
@app.route('/admin/group/<int:group_id>/add_student', methods=['POST'])
def add_student_to_group(group_id):
    if session.get('role') != 'Администратор':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))
    
    full_name = request.form['full_name']
    login = request.form['login']
    password = request.form['password']
    
    # Проверяем, существует ли пользователь с таким логином
    check_query = "SELECT id FROM users WHERE login = %s"
    existing = db.execute_query(check_query, (login,))
    
    if existing:
        flash('Пользователь с таким логином уже существует')
        return redirect(url_for('edit_group', group_id=group_id))
    
    # Добавляем студента
    query = """
    INSERT INTO users (login, password_hash, full_name, role, group_id)
    VALUES (%s, %s, %s, 'Студент', %s)
    """
    
    if db.execute_insert(query, (login, password, full_name, group_id)):
        flash('Студент добавлен в группу')
    
    return redirect(url_for('edit_group', group_id=group_id))

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========

if __name__ == '__main__':
    # Проверяем соединение с БД при запуске
    if not db.connect():
        print("Внимание: не удалось подключиться к базе данных!")
        print("Приложение будет работать с ограниченной функциональностью.")
    else:
        print("Соединение с базой данных установлено успешно!")
    
    app.run(debug=True, port=5001)
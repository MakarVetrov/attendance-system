# 🎓 Система учёта посещаемости студентов

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.3%2B-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-13%2B-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

Веб-приложение для автоматизации учёта посещаемости студентов с поддержкой трёх ролей: администратор, преподаватель, студент.

## 🚀 Быстрый старт

### 1. Клонирование и установка
```
git clone https://github.com/ВАШ_ЛОГИН/attendance-system.git
cd attendance-system
python -m venv venv
```
#### Активация виртуального окружения
```
venv\Scripts\activate  # Windows
```
#### source venv/bin/activate  # Linux/Mac
```
pip install -r requirements.txt
```
### 2. Настройка PostgreSQL

#### В psql от имени postgres:
```
CREATE DATABASE attendance_db;
CREATE USER postgres WITH PASSWORD 'ваш_пароль';
GRANT ALL PRIVILEGES ON DATABASE attendance_db TO postgres;
```
#### Инициализация БД:
```
psql -U postgres -d attendance_db -f "Создание БД.txt"
```
### 3. Настройка окружения
#### Создайте файл .env в корне проекта:
```
DB_HOST=localhost
DB_NAME=attendance_db
DB_USER=postgres
DB_PASSWORD=ваш_пароль
SECRET_KEY=сгенерируйте_ключ
```
### 4. Запуск приложения
```
python main.py
```
#### Откройте в браузере: http://localhost:5001

### 5. Тестовые аккаунты

| Роль | Логин | Пароль | Доступ |
|------|-------|--------|--------|
| 👑 Администратор | `admin` | `admin123` | Полный доступ |
| 👨‍🏫 Преподаватель | `teacher1` | `teacher123` | Управление занятиями |
| 👨‍🎓 Студент | `student1` | `student123` | Просмотр посещаемости |

import os
import sys

def save_files_with_content(directory, output_file='files_with_content.txt', 
                           max_file_size=1024*1024):  # 1MB по умолчанию
    """
    Сохраняет пути и содержимое текстовых файлов
    """
    text_extensions = {'.txt', '.py', '.html', '.css', '.js', '.json', '.xml', 
                      '.csv', '.md', '.yml', '.yaml', '.ini', '.cfg', '.conf'}
    
    directory = os.path.abspath(directory)
    
    with open(output_file, 'w', encoding='utf-8') as out_f:
        out_f.write(f"СКАНИРОВАНИЕ ДИРЕКТОРИИ: {directory}\n")
        out_f.write("=" * 100 + "\n\n")
        
        total_files = 0
        scanned_files = 0
        
        for root, dirs, files in os.walk(directory):
            # Пропускаем служебные папки
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', 'venv'}]
            
            for file in files:
                total_files += 1
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, directory)
                
                # Пропускаем бинарные и большие файлы
                ext = os.path.splitext(file)[1].lower()
                if ext not in text_extensions:
                    continue
                
                try:
                    file_size = os.path.getsize(file_path)
                    if file_size > max_file_size:
                        out_f.write(f"\nФАЙЛ: {rel_path}\n")
                        out_f.write(f"РАЗМЕР: {file_size} байт (пропущен - слишком большой)\n")
                        out_f.write("-" * 80 + "\n\n")
                        continue
                    
                    out_f.write(f"\n{'='*80}\n")
                    out_f.write(f"ФАЙЛ: {rel_path}\n")
                    out_f.write(f"ПОЛНЫЙ ПУТЬ: {file_path}\n")
                    out_f.write(f"РАЗМЕР: {file_size} байт\n")
                    out_f.write(f"{'='*80}\n\n")
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as in_f:
                            content = in_f.read()
                            out_f.write(content)
                            if not content.endswith('\n'):
                                out_f.write('\n')
                    except UnicodeDecodeError:
                        out_f.write("[Бинарный файл или неизвестная кодировка]\n")
                    except Exception as e:
                        out_f.write(f"[Ошибка чтения: {str(e)}]\n")
                    
                    scanned_files += 1
                    
                except Exception as e:
                    out_f.write(f"\nОШИБКА при обработке {rel_path}: {str(e)}\n")
    
    print(f"✓ Всего файлов в директории: {total_files}")
    print(f"✓ Обработано текстовых файлов: {scanned_files}")
    print(f"✓ Результат сохранен в: {output_file}")

if __name__ == "__main__":
    # Использование
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = input("Введите путь к директории: ").strip() or "."
    
    save_files_with_content(directory, 'directory_contents.txt')
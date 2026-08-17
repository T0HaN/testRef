import os

# Укажите путь к корневой директории, в которой нужно искать HTML-файлы.
# Например: TARGET_DIR = "/home/user/project" или TARGET_DIR = "."
TARGET_DIR = "templates"  # <-- измените на свой путь

OLD = '<link rel="icon" href="/images/Logo.ico" type="image/x-icon">'
NEW = '<link rel="icon" href="/static/images/Logo.ico" type="image/x-icon">'

def replace_in_file(filepath: str) -> bool:
    """Заменяет строку в файле, если она присутствует. Возвращает True, если замена выполнена."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, IOError) as e:
        print(f'Пропуск {filepath}: ошибка чтения ({e})')
        return False

    if OLD not in content:
        return False

    new_content = content.replace(OLD, NEW)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    except IOError as e:
        print(f'Ошибка записи {filepath}: {e}')
        return False

def main():
    if not os.path.isdir(TARGET_DIR):
        print(f'Ошибка: "{TARGET_DIR}" не является директорией')
        return

    count = 0
    for dirpath, _, filenames in os.walk(TARGET_DIR):
        for filename in filenames:
            if filename.lower().endswith(('.html', '.htm')):
                filepath = os.path.join(dirpath, filename)
                if replace_in_file(filepath):
                    print(f'Заменено: {filepath}')
                    count += 1

    print(f'Готово. Обработано файлов: {count}')

if __name__ == '__main__':
    main()
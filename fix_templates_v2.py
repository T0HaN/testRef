#!/usr/bin/env python3
"""
Умный скрипт для исправления вызовов templates.TemplateResponse.
Использует AST для надёжного парсинга и преобразования кода.

Старый синтаксис: templates.TemplateResponse("имя.html", context={...})
Новый синтаксис: templates.TemplateResponse(request, "имя.html", context={...})

Также убирает "request": request из context.
"""

import ast
import re
from pathlib import Path


def fix_template_responses(source_code: str) -> str:
    """Преобразует все вызовы TemplateResponse в коде"""
    
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        print(f"❌ Ошибка парсинга исходного файла: {e}")
        print("   Сначала восстанови main.py из git/бэкапа!")
        return None
    
    # Собираем все вызовы TemplateResponse с их позициями
    replacements = []
    
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        
        # Проверяем, что это вызов templates.TemplateResponse
        func = node.func
        is_template_response = False
        
        if isinstance(func, ast.Attribute):
            if func.attr == 'TemplateResponse':
                if isinstance(func.value, ast.Name) and func.value.id == 'templates':
                    is_template_response = True
        
        if not is_template_response:
            continue
        
        # Проверяем, что первый аргумент — строка (старый синтаксис)
        if not node.args:
            continue
        
        first_arg = node.args[0]
        if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
            # Первый аргумент уже не строка — возможно, уже исправлено
            continue
        
        template_name = first_arg.value
        
        # Проверяем, есть ли уже request как первый аргумент
        if len(node.args) >= 2 and isinstance(node.args[0], ast.Name) and node.args[0].id == 'request':
            continue  # Уже исправлено
        
        # Находим позицию вызова в исходнике
        start_line = node.lineno
        end_line = node.end_lineno
        start_col = node.col_offset
        end_col = node.end_col_offset
        
        # Извлекаем исходный текст вызова
        lines = source_code.split('\n')
        if start_line == end_line:
            original_call = lines[start_line - 1][start_col:end_col]
        else:
            call_lines = [lines[start_line - 1][start_col:]]
            for i in range(start_line, end_line - 1):
                call_lines.append(lines[i])
            call_lines.append(lines[end_line - 1][:end_col])
            original_call = '\n'.join(call_lines)
        
        # Теперь преобразуем вызов
        new_call = transform_call(original_call, template_name)
        
        if new_call:
            replacements.append({
                'start_line': start_line,
                'start_col': start_col,
                'end_line': end_line,
                'end_col': end_col,
                'original': original_call,
                'new': new_call
            })
    
    if not replacements:
        print("ℹ️  Вызовов для исправления не найдено (возможно, уже всё исправлено)")
        return source_code
    
    # Применяем замены С КОНЦА, чтобы не сбить позиции
    lines = source_code.split('\n')
    
    # Сортируем по убыванию позиций
    replacements.sort(key=lambda r: (r['start_line'], r['start_col']), reverse=True)
    
    for r in replacements:
        start_line = r['start_line']
        end_line = r['end_line']
        start_col = r['start_col']
        end_col = r['end_col']
        
        if start_line == end_line:
            # Однострочный вызов
            line = lines[start_line - 1]
            lines[start_line - 1] = line[:start_col] + r['new'] + line[end_col:]
        else:
            # Многострочный вызов
            first_line = lines[start_line - 1]
            last_line = lines[end_line - 1]
            
            new_first = first_line[:start_col] + r['new']
            new_last = last_line[end_col:]
            
            # Заменяем диапазон строк
            lines[start_line - 1:end_line] = [new_first + new_last]
    
    return '\n'.join(lines)


def transform_call(original_call: str, template_name: str) -> str:
    """Преобразует один вызов TemplateResponse"""
    
    # Находим context={...} в вызове, учитывая вложенные скобки
    context_match = re.search(r'context\s*=\s*\{', original_call)
    
    if not context_match:
        # Нет context — просто добавляем request первым аргументом
        # Ищем первую открывающую скобку после TemplateResponse
        match = re.match(r'(templates\.TemplateResponse\s*\()', original_call)
        if match:
            return original_call[:match.end()] + 'request, ' + original_call[match.end():]
        return original_call
    
    # Извлекаем содержимое context с учётом вложенных скобок
    ctx_start = context_match.end() - 1  # позиция {
    ctx_content, ctx_end = extract_balanced_braces(original_call, ctx_start)
    
    if ctx_content is None:
        print(f"   ⚠️  Не удалось извлечь context в вызове")
        return None
    
    # Убираем "request": request из context
    ctx_content = remove_request_from_context(ctx_content)
    
    # Собираем новый вызов
    # Берём часть до context=
    before_context = original_call[:context_match.start()].rstrip()
    
    # Берём часть после context={...}
    after_context = original_call[ctx_end + 1:]
    
    # Находим имя шаблона в before_context
    # Убираем старое имя шаблона
    before_context = re.sub(
        r'templates\.TemplateResponse\s*\(\s*["\'][^"\']+["\']\s*,?\s*',
        'templates.TemplateResponse(request, "' + template_name + '", ',
        before_context
    )
    
    # Собираем новый вызов
    new_call = before_context + 'context={' + ctx_content + '}' + after_context
    
    return new_call


def extract_balanced_braces(text: str, start_pos: int) -> tuple:
    """Извлекает содержимое {...} с учётом вложенности. Возвращает (содержимое, позиция закрывающей })"""
    if start_pos >= len(text) or text[start_pos] != '{':
        return None, -1
    
    depth = 0
    in_string = False
    string_char = None
    escape_next = False
    i = start_pos
    
    while i < len(text):
        ch = text[i]
        
        if escape_next:
            escape_next = False
            i += 1
            continue
        
        if ch == '\\':
            escape_next = True
            i += 1
            continue
        
        if in_string:
            if ch == string_char:
                in_string = False
            i += 1
            continue
        
        if ch in ('"', "'"):
            in_string = True
            string_char = ch
            i += 1
            continue
        
        if ch == '{':
            if depth == 0:
                content_start = i + 1
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[content_start:i], i
        
        i += 1
    
    return None, -1


def remove_request_from_context(ctx_content: str) -> str:
    """Убирает 'request': request или "request": request из context"""
    # Паттерн с учётом возможных пробелов и запятых
    patterns = [
        r'"request"\s*:\s*request\s*,?\s*',
        r"'request'\s*:\s*request\s*,?\s*",
    ]
    
    result = ctx_content
    for pattern in patterns:
        result = re.sub(pattern, '', result)
    
    # Убираем запятую в начале, если осталась
    result = re.sub(r'^\s*,\s*', '', result)
    # Убираем запятую в конце
    result = re.sub(r',\s*$', '', result)
    
    return result


def main():
    filepath = Path('/root/DiceCloud/DC1.2/main.py')
    
    if not filepath.exists():
        print(f"❌ Файл не найден: {filepath}")
        return
    
    # Создаём бэкап
    backup_path = filepath.with_suffix('.py.backup')
    source = filepath.read_text(encoding='utf-8')
    backup_path.write_text(source, encoding='utf-8')
    print(f"💾 Бэкап создан: {backup_path}")
    
    # Преобразуем
    new_source = fix_template_responses(source)
    
    if new_source is None:
        print("❌ Не удалось преобразовать файл")
        return
    
    if new_source == source:
        print("ℹ️  Изменений не требуется")
        return
    
    # Проверяем синтаксис нового кода
    try:
        ast.parse(new_source)
        print("✅ Синтаксис нового кода корректен")
    except SyntaxError as e:
        print(f"❌ Ошибка синтаксиса в преобразованном коде: {e}")
        print("   Файл НЕ был изменён. Бэкап доступен.")
        return
    
    # Сохраняем
    filepath.write_text(new_source, encoding='utf-8')
    
    # Считаем изменения
    old_count = source.count('templates.TemplateResponse')
    new_count = new_source.count('templates.TemplateResponse')
    print(f"✅ Файл обновлён! Вызовов TemplateResponse: {new_count}")
    print(f"📝 Проверь результат: {filepath}")


if __name__ == '__main__':
    main()

import re
import sys

filename = 'main.py'

with open(filename, 'r', encoding='utf-8') as f:
    content = f.read()

# Паттерн: templates.TemplateResponse("имя.html", context={...})
pattern = r'templates\.TemplateResponse\(\s*"([^"]+)"\s*,\s*context=\{([^}]*)\}\s*\)'

count = 0

def replace_func(match):
    global count
    template_name = match.group(1)
    context_content = match.group(2).strip()
    
    # Убираем "request": request из контекста
    context_content = re.sub(r'"request"\s*:\s*request\s*,?\s*', '', context_content)
    context_content = re.sub(r',\s*$', '', context_content)  # Убираем запятую в конце
    
    count += 1
    if context_content:
        return f'templates.TemplateResponse(request, "{template_name}", context={{{context_content}}})'
    else:
        return f'templates.TemplateResponse(request, "{template_name}", context={{}})'

new_content = re.sub(pattern, replace_func, content)

# Также обрабатываем случай, где context передаётся позиционно (без ключевого слова)
pattern2 = r'templates\.TemplateResponse\(\s*"([^"]+)"\s*,\s*\{([^}]*)\}\s*\)'

def replace_func2(match):
    global count
    template_name = match.group(1)
    context_content = match.group(2).strip()
    context_content = re.sub(r'"request"\s*:\s*request\s*,?\s*', '', context_content)
    context_content = re.sub(r',\s*$', '', context_content)
    count += 1
    if context_content:
        return f'templates.TemplateResponse(request, "{template_name}", context={{{context_content}}})'
    else:
        return f'templates.TemplateResponse(request, "{template_name}", context={{}})'

new_content = re.sub(pattern2, replace_func2, new_content)

with open(filename, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"✅ Исправлено {count} вызовов TemplateResponse в {filename}")

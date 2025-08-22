#!/bin/bash
# Скрипт для авторизации в GitHub

echo "Вставьте ваш GitHub Personal Access Token:"
read -s GITHUB_TOKEN

echo $GITHUB_TOKEN | gh auth login --with-token

if [ $? -eq 0 ]; then
    echo "✅ Авторизация успешна!"
    echo "Теперь загружаем проект на GitHub..."
    
    # Создаем репозиторий и пушим
    gh repo create tg-bot --public --source=. --push --description "Telegram bot with Django admin panel"
    
    if [ $? -eq 0 ]; then
        echo "✅ Проект успешно загружен!"
        echo "📎 Ссылка: https://github.com/osvayder/tg-bot"
    else
        # Если репозиторий уже существует, просто пушим
        git push -u origin main
        echo "📎 Проект обновлен: https://github.com/osvayder/tg-bot"
    fi
else
    echo "❌ Ошибка авторизации. Проверьте токен."
fi
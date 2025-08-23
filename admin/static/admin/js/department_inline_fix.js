// Исправление для кнопки "+" в inline формах департаментов
document.addEventListener('DOMContentLoaded', function() {
    // Находим все кнопки добавления в inline формах
    const inlineGroups = document.querySelectorAll('.inline-group');
    
    inlineGroups.forEach(function(group) {
        // Проверяем, что это inline для поддепартаментов
        if (group.id && group.id.includes('children')) {
            // Находим кнопку "+" (add-related)
            const addButtons = group.querySelectorAll('.add-related, .addlink');
            
            addButtons.forEach(function(button) {
                // Получаем ID родительского департамента из URL
                const match = window.location.pathname.match(/\/department\/(\d+)\//);
                if (match) {
                    const parentId = match[1];
                    // Обновляем href кнопки, добавляя parent параметр
                    const originalHref = button.href;
                    if (originalHref && !originalHref.includes('parent=')) {
                        button.href = originalHref + '?parent=' + parentId;
                    }
                }
            });
        }
    });
});
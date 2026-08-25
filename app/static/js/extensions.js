document.addEventListener('DOMContentLoaded', () => {
    const connectForm = document.getElementById('connect-extension-form');
    connectForm?.addEventListener('submit', async event => {
        event.preventDefault();
        const button = document.getElementById('connect-extension-button');
        const log = document.getElementById('connection-log');
        const body = Object.fromEntries(new FormData(connectForm).entries());
        button.disabled = true;
        log.textContent = 'Проверка параметров подключения…\n';
        try {
            const response = await fetch('/api/extensions/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
            log.textContent = `${result.logs.join('\n')}\nГотово: всё прошло нормально.`;
            setTimeout(() => window.location.reload(), 1200);
        } catch (error) {
            log.textContent += `Ошибка: ${error.message}\n`;
            button.disabled = false;
        }
    });

    document.querySelectorAll('.extension-toggle').forEach(toggle => {
        toggle.addEventListener('change', async () => {
            const card = toggle.closest('[data-extension-id]');
            toggle.disabled = true;
            try {
                const response = await fetch(`/api/extensions/${card.dataset.extensionId}`, {
                    method: 'PATCH',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({enabled: toggle.checked}),
                });
                if (!response.ok) throw new Error((await response.json()).detail || `HTTP ${response.status}`);
                window.location.reload();
            } catch (error) {
                toggle.checked = !toggle.checked;
                toggle.disabled = false;
                showToast(`Не удалось изменить подключение: ${error.message}`, 'danger');
            }
        });
    });

    const form = document.getElementById('deploy-extension-form');
    form?.addEventListener('submit', async event => {
        event.preventDefault();
        const button = document.getElementById('deploy-extension-button');
        const log = document.getElementById('deployment-log');
        const body = Object.fromEntries(new FormData(form).entries());
        button.disabled = true;
        log.textContent = 'Создание операции подключения…\n';
        try {
            const response = await fetch('/api/extensions/deploy', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
            });
            if (!response.ok) throw new Error((await response.json()).detail || `HTTP ${response.status}`);
            const {job_id: jobId} = await response.json();
            const events = new EventSource(`/api/extensions/jobs/${jobId}/events`);
            events.onmessage = message => {
                log.textContent += `${JSON.parse(message.data).message}\n`;
                log.scrollTop = log.scrollHeight;
            };
            events.addEventListener('done', message => {
                const {status} = JSON.parse(message.data);
                events.close();
                button.disabled = false;
                if (status === 'complete') setTimeout(() => window.location.reload(), 1200);
            });
            events.onerror = () => { events.close(); button.disabled = false; };
        } catch (error) {
            log.textContent += `Ошибка: ${error.message}\n`;
            button.disabled = false;
        }
    });
});

(() => {
    const roots = document.querySelectorAll('[data-customizable-dashboard]');
    if (!roots.length) return;

    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    let preferences = {};
    try {
        preferences = JSON.parse(document.body.dataset.dashboardPreferences || '{}');
    } catch (error) {
        preferences = {};
    }

    function slug(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-|-$/g, '')
            .slice(0, 70);
    }

    function widgetLabel(element, index) {
        if (element.dataset.dashboardLabel) return element.dataset.dashboardLabel;
        const heading = element.querySelector('h2, h3, .ds-section-label');
        if (heading?.textContent.trim()) return heading.textContent.trim();
        if (element.classList.contains('grid')) return 'Resumo e indicadores';
        return `Bloco ${index + 1}`;
    }

    roots.forEach((root, rootIndex) => {
        const dashboardKey = slug(root.dataset.dashboardKey || window.location.pathname) || `dashboard-${rootIndex + 1}`;
        const usedIds = new Set();
        const explicitWidgets = Array.from(root.querySelectorAll('[data-dashboard-widget]')).filter(element => {
            const parentWidget = element.parentElement?.closest('[data-dashboard-widget]');
            return !parentWidget || !root.contains(parentWidget);
        });
        const widgetElements = explicitWidgets.length ? explicitWidgets : Array.from(root.children).filter(element => {
            if (!['DIV', 'SECTION', 'ARTICLE'].includes(element.tagName)) return false;
            if (element === root.firstElementChild) return false;
            if (element.hasAttribute('data-dashboard-fixed')) return false;
            if (element.classList.contains('ds-page-header')) return false;
            if (element.matches('header:first-child')) return false;
            return true;
        });
        const widgets = widgetElements.map((element, index) => {
            const label = widgetLabel(element, index);
            let id = slug(element.dataset.dashboardWidget || element.dataset.dashboardPanel || label) || `bloco-${index + 1}`;
            if (usedIds.has(id)) id = `${id}-${index + 1}`;
            usedIds.add(id);
            element.dataset.dashboardWidget = id;
            return {element, id, label};
        });

        if (!widgets.length) return;
        let savedHidden = new Set(Array.isArray(preferences[dashboardKey]) ? preferences[dashboardKey] : []);

        function applyHidden(hidden) {
            widgets.forEach(widget => {
                const isHidden = hidden.has(widget.id);
                widget.element.classList.toggle('dashboard-widget-hidden', isHidden);
                if (widget.element.dataset.dashboardPanel) {
                    const tab = root.querySelector(`[data-dashboard-tab="${widget.element.dataset.dashboardPanel}"]`);
                    if (tab) {
                        tab.hidden = isHidden;
                        widget.element.hidden = isHidden || tab.getAttribute('aria-selected') !== 'true';
                    }
                } else {
                    widget.element.hidden = isHidden;
                }
            });
            const selectedHiddenTab = root.querySelector('[data-dashboard-tab][aria-selected="true"][hidden]');
            const firstVisibleTab = root.querySelector('[data-dashboard-tab]:not([hidden])');
            if (selectedHiddenTab && firstVisibleTab) firstVisibleTab.click();
        }
        applyHidden(savedHidden);

        const bar = document.createElement('div');
        bar.className = 'dashboard-customizer-bar';
        bar.setAttribute('data-dashboard-fixed', '');
        const summary = document.createElement('span');
        summary.className = 'dashboard-customizer-summary';
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'ds-button ds-button-secondary ds-button-sm dashboard-customizer-open';
        button.textContent = 'Personalizar página';
        bar.append(summary, button);

        const firstContent = Array.from(root.children).find(element => !element.hasAttribute('data-dashboard-fixed'));
        root.insertBefore(bar, firstContent || null);

        function updateSummary() {
            const visible = widgets.length - savedHidden.size;
            summary.textContent = `${visible} de ${widgets.length} blocos visíveis`;
        }
        updateSummary();

        const dialog = document.createElement('dialog');
        dialog.className = 'dashboard-customizer-dialog';
        dialog.setAttribute('aria-labelledby', `dashboard-customizer-title-${rootIndex}`);
        const shell = document.createElement('div');
        shell.className = 'dashboard-customizer-shell';
        const header = document.createElement('header');
        const headerText = document.createElement('div');
        const eyebrow = document.createElement('p');
        eyebrow.textContent = 'Preferências da página';
        const title = document.createElement('h2');
        title.id = `dashboard-customizer-title-${rootIndex}`;
        title.textContent = 'Escolher informação visível';
        headerText.append(eyebrow, title);
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'dashboard-customizer-close';
        close.setAttribute('aria-label', 'Fechar');
        close.textContent = '×';
        header.append(headerText, close);

        const intro = document.createElement('p');
        intro.className = 'dashboard-customizer-intro';
        intro.textContent = 'Seleciona os blocos que queres manter nesta página. A escolha fica guardada na tua conta.';
        const list = document.createElement('div');
        list.className = 'dashboard-customizer-list';
        const checkboxes = new Map();
        widgets.forEach(widget => {
            const label = document.createElement('label');
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = !savedHidden.has(widget.id);
            checkbox.value = widget.id;
            const text = document.createElement('span');
            text.textContent = widget.label;
            label.append(checkbox, text);
            list.append(label);
            checkboxes.set(widget.id, checkbox);
        });

        const feedback = document.createElement('p');
        feedback.className = 'dashboard-customizer-feedback';
        feedback.setAttribute('role', 'status');
        const footer = document.createElement('footer');
        const reset = document.createElement('button');
        reset.type = 'button';
        reset.className = 'ds-button ds-button-secondary';
        reset.textContent = 'Repor padrão';
        const save = document.createElement('button');
        save.type = 'button';
        save.className = 'ds-button ds-button-primary';
        save.textContent = 'Guardar visualização';
        footer.append(reset, save);
        shell.append(header, intro, list, feedback, footer);
        dialog.append(shell);
        document.body.append(dialog);

        function selectedHidden() {
            return new Set(Array.from(checkboxes.entries())
                .filter(([, checkbox]) => !checkbox.checked)
                .map(([id]) => id));
        }

        function restoreSaved() {
            checkboxes.forEach((checkbox, id) => {
                checkbox.checked = !savedHidden.has(id);
            });
            applyHidden(savedHidden);
        }

        checkboxes.forEach(checkbox => checkbox.addEventListener('change', () => {
            applyHidden(selectedHidden());
        }));
        button.addEventListener('click', () => {
            feedback.textContent = '';
            restoreSaved();
            dialog.showModal();
        });
        close.addEventListener('click', () => {
            restoreSaved();
            dialog.close();
        });
        dialog.addEventListener('cancel', event => {
            event.preventDefault();
            restoreSaved();
            dialog.close();
        });
        reset.addEventListener('click', () => {
            checkboxes.forEach(checkbox => { checkbox.checked = true; });
            applyHidden(new Set());
            feedback.textContent = 'Visualização padrão selecionada.';
        });
        save.addEventListener('click', async () => {
            const hidden = selectedHidden();
            save.disabled = true;
            feedback.textContent = 'A guardar…';
            try {
                const response = await fetch('/dashboard/preferencias', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        ...(csrf ? {'X-CSRF-Token': csrf} : {})
                    },
                    body: JSON.stringify({dashboard: dashboardKey, ocultos: Array.from(hidden)})
                });
                const data = await response.json();
                if (!response.ok || !data.sucesso) throw new Error(data.erro || 'Não foi possível guardar a visualização.');
                savedHidden = hidden;
                preferences[dashboardKey] = Array.from(hidden);
                applyHidden(savedHidden);
                updateSummary();
                dialog.close();
            } catch (error) {
                feedback.textContent = error.message || 'Não foi possível guardar a visualização.';
            } finally {
                save.disabled = false;
            }
        });
    });
})();

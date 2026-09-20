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
        const visibleSummary = document.createElement('span');
        visibleSummary.className = 'dashboard-customizer-summary';
        const menu = document.createElement('details');
        menu.className = 'dashboard-customizer-menu';
        const trigger = document.createElement('summary');
        trigger.className = 'ds-button ds-button-secondary ds-button-sm dashboard-customizer-trigger';
        trigger.innerHTML = '<span>Personalizar página</span><i aria-hidden="true"></i>';
        const panel = document.createElement('div');
        panel.className = 'dashboard-customizer-panel';

        const header = document.createElement('header');
        const headerText = document.createElement('div');
        const eyebrow = document.createElement('p');
        eyebrow.textContent = 'Preferências da página';
        const title = document.createElement('h2');
        title.textContent = 'Escolher informação visível';
        headerText.append(eyebrow, title);
        header.append(headerText);

        const intro = document.createElement('p');
        intro.className = 'dashboard-customizer-intro';
        intro.textContent = 'Seleciona os blocos que queres manter. A escolha fica guardada na tua conta.';
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
        reset.className = 'ds-button ds-button-secondary ds-button-sm';
        reset.textContent = 'Repor padrão';
        const save = document.createElement('button');
        save.type = 'button';
        save.className = 'ds-button ds-button-primary ds-button-sm';
        save.textContent = 'Guardar';
        footer.append(reset, save);
        panel.append(header, intro, list, feedback, footer);
        menu.append(trigger, panel);
        bar.append(visibleSummary, menu);

        const anchor = root.querySelector('[data-dashboard-customizer-anchor]');
        if (anchor) {
            bar.classList.add('is-inline');
            anchor.append(bar);
        } else {
            const firstContent = Array.from(root.children).find(element => !element.hasAttribute('data-dashboard-fixed'));
            root.insertBefore(bar, firstContent || null);
        }

        function updateSummary() {
            const visible = widgets.length - savedHidden.size;
            visibleSummary.textContent = `${visible} de ${widgets.length} blocos visíveis`;
        }
        updateSummary();

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
        menu.addEventListener('toggle', () => {
            if (menu.open) {
                document.querySelectorAll('.dashboard-customizer-menu[open]').forEach(other => {
                    if (other !== menu) other.open = false;
                });
                feedback.textContent = '';
                restoreSaved();
            } else {
                restoreSaved();
            }
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
                    credentials: 'same-origin',
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
                menu.open = false;
            } catch (error) {
                feedback.textContent = error.message || 'Não foi possível guardar a visualização.';
            } finally {
                save.disabled = false;
            }
        });
        document.addEventListener('click', event => {
            if (menu.open && !menu.contains(event.target)) menu.open = false;
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && menu.open) menu.open = false;
        });
    });
})();

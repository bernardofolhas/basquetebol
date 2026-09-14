(function () {
    const sidebar = document.getElementById('app-sidebar');
    const open = document.getElementById('sidebar-open');
    const close = document.getElementById('sidebar-close');
    const overlay = document.getElementById('sidebar-overlay');
    const scroll = document.getElementById('sidebar-scroll');
    const inbox = document.getElementById('sidebar-inbox-dialog');
    if (!sidebar || !open || !close || !overlay || !scroll) return;
    document.querySelector('[data-inbox-open]')?.addEventListener('click', () => inbox.showModal());
    document.querySelector('[data-inbox-close]')?.addEventListener('click', () => inbox.close());
    const mobile = window.matchMedia('(max-width: 900px)');
    let desktopHidden = false;
    try { desktopHidden = localStorage.getItem('sidebar-hidden') === 'true'; } catch (_) {}
    function setHidden(hidden, remember) {
        document.body.classList.toggle('sidebar-hidden', hidden);
        document.body.classList.toggle('sidebar-mobile-open', !hidden && mobile.matches);
        overlay.hidden = hidden || !mobile.matches;
        const content = document.getElementById('conteudo-principal');
        if (content) content.inert = !hidden && mobile.matches;
        open.setAttribute('aria-expanded', String(!hidden));
        if (remember && !mobile.matches) {
            desktopHidden = hidden;
            try { localStorage.setItem('sidebar-hidden', String(hidden)); } catch (_) {}
        }
    }
    setHidden(mobile.matches || desktopHidden, false);
    open.addEventListener('click', () => { setHidden(false, true); close.focus(); });
    function hide() { setHidden(true, true); open.focus(); }
    close.addEventListener('click', hide);
    overlay.addEventListener('click', hide);
    mobile.addEventListener('change', () => setHidden(mobile.matches || desktopHidden, false));
    document.addEventListener('keydown', event => {
        if (document.querySelector('dialog[open]')) return;
        if (document.body.classList.contains('sidebar-hidden')) return;
        if (event.key === 'Escape' && !document.querySelector('dialog[open]')) hide();
        if (event.key !== 'Tab' || !mobile.matches) return;
        const items = Array.from(sidebar.querySelectorAll('a,button,input')).filter(el => el.getClientRects().length && !el.disabled);
        const first = items[0], last = items[items.length - 1];
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    try { scroll.scrollTop = Number(sessionStorage.getItem('sidebar-scroll') || 0); } catch (_) {}
    scroll.addEventListener('scroll', () => {
        try { sessionStorage.setItem('sidebar-scroll', String(scroll.scrollTop)); } catch (_) {}
    }, {passive:true});
    const links = Array.from(sidebar.querySelectorAll('a.sidebar-link,a.sidebar-heading'));
    const candidates = links.map(link => {
        const url = new URL(link.href, location.href);
        const queryMatches = Array.from(url.searchParams).every(([key, value]) => new URLSearchParams(location.search).get(key) === value);
        const exact = url.pathname === location.pathname && queryMatches;
        return { link, score: exact ? 1000 + url.search.length : link.classList.contains('is-active') ? 1 : 0 };
    }).sort((a, b) => b.score - a.score);
    links.forEach(link => { link.classList.remove('is-active'); link.removeAttribute('aria-current'); });
    if (candidates[0]?.score) {
        candidates[0].link.classList.add('is-active'); candidates[0].link.setAttribute('aria-current', 'page');
    }
    const groups = Array.from(sidebar.querySelectorAll('details[data-sidebar-section]'));
    const activeGroup = candidates[0]?.score
        ? candidates[0].link.closest('details[data-sidebar-section]')
        : sidebar.querySelector('details[data-sidebar-section] > summary.is-active')?.parentElement;
    let storedGroup = '';
    try { storedGroup = localStorage.getItem('sidebar-open-section') || ''; } catch (_) {}
    const initialGroup = activeGroup?.dataset.sidebarSection || storedGroup;
    groups.forEach(group => { group.open = group.dataset.sidebarSection === initialGroup; });
    groups.forEach(group => {
        group.addEventListener('toggle', () => {
            if (group.open) {
                groups.forEach(other => { if (other !== group) other.open = false; });
                try { localStorage.setItem('sidebar-open-section', group.dataset.sidebarSection); } catch (_) {}
            } else if (!groups.some(other => other.open)) {
                try { localStorage.removeItem('sidebar-open-section'); } catch (_) {}
            }
        });
    });
    sidebar.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => { if (mobile.matches) setHidden(true, false); });
    });
})();

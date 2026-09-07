(function () {
    const sidebar = document.getElementById('app-sidebar');
    const open = document.getElementById('sidebar-open');
    const close = document.getElementById('sidebar-close');
    const overlay = document.getElementById('sidebar-overlay');
    const scroll = document.getElementById('sidebar-scroll');
    const mobile = window.matchMedia('(max-width: 900px)');
    let desktopHidden = false;
    try { desktopHidden = localStorage.getItem('sidebar-hidden') === 'true'; } catch (_) {}
    function setHidden(hidden, remember) {
        document.body.classList.toggle('sidebar-hidden', hidden);
        document.body.classList.toggle('sidebar-mobile-open', !hidden && mobile.matches);
        overlay.hidden = hidden || !mobile.matches;
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
        if (document.body.classList.contains('sidebar-hidden')) return;
        if (event.key === 'Escape' && !document.querySelector('dialog[open]')) hide();
        if (event.key !== 'Tab' || !mobile.matches) return;
        const items = Array.from(sidebar.querySelectorAll('a,button,input')).filter(el => el.getClientRects().length && !el.disabled);
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    try { scroll.scrollTop = Number(sessionStorage.getItem('sidebar-scroll') || 0); } catch (_) {}
    scroll.addEventListener('scroll', () => {
        try { sessionStorage.setItem('sidebar-scroll', String(scroll.scrollTop)); } catch (_) {}
    }, {passive:true});
    sidebar.querySelectorAll('a').forEach(link => {
        if (link.getAttribute('href') === location.pathname + location.search) {
            link.classList.add('is-active');
            link.setAttribute('aria-current', 'page');
        }
        link.addEventListener('click', () => { if (mobile.matches) setHidden(true, false); });
    });
})();

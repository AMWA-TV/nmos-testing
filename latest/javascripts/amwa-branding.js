(() => {
  const header = document.querySelector('.md-header__inner') || document.querySelector('header');
  if (!header || header.querySelector('.amwa-header-branding')) return;

  const scriptUrl = document.currentScript && document.currentScript.src;
  const assetUrl = (file) => new URL(`../images/${file}`, scriptUrl || window.location.href).href;
  const branding = document.createElement('div');
  branding.className = 'amwa-header-branding';
  branding.setAttribute('aria-label', 'AMWA branding');

  for (const logo of [{"file": "AMWA-logo.png", "alt": "AMWA logo", "href": "https://www.amwa.tv"}]) {
    const image = document.createElement('img');
    image.src = logo.src || assetUrl(logo.file);
    image.alt = logo.alt;
    if (logo.href) {
      const link = document.createElement('a');
      link.href = logo.href;
      link.setAttribute('aria-label', logo.alt);
      link.appendChild(image);
      branding.appendChild(link);
    } else {
      branding.appendChild(image);
    }
  }

  header.insertBefore(branding, header.firstChild);

  const normalisePath = (path) => {
    const trimmed = path.replace(/index\.html$/, '').replace(/\/+$/, '');
    return `${trimmed}/`;
  };
  const currentPath = normalisePath(window.location.pathname);
  document.querySelectorAll('.md-sidebar--primary a.md-nav__link').forEach((link) => {
    const target = new URL(link.href, window.location.href);
    if (target.origin === window.location.origin && normalisePath(target.pathname) === currentPath) {
      link.classList.add('amwa-current-page');
    }
  });
})();

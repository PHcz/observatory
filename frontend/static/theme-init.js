// Apply the saved theme before first paint (no light/dark flash). Loaded as a
// blocking file rather than inline so the page's CSP needs no inline-script
// allowance for it (security audit F55).
(function () {
	try {
		var raw = localStorage.getItem('observatory.settings.v1');
		var theme = 'auto';
		if (raw) {
			var parsed = JSON.parse(raw);
			if (parsed && (parsed.theme === 'light' || parsed.theme === 'dark' || parsed.theme === 'auto')) {
				theme = parsed.theme;
			}
		}
		var resolved = theme;
		if (theme === 'auto') {
			resolved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
		}
		document.documentElement.dataset.theme = resolved;
	} catch (e) {
		document.documentElement.dataset.theme = 'light';
	}
})();

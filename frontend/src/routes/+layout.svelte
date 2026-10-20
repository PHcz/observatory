<script lang="ts">
	// Inter is bundled (was Google Fonts: a request per page view, broken offline).
	import '@fontsource/inter/400.css';
	import '@fontsource/inter/600.css';
	import '../app.css';
	import favicon from '#lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}

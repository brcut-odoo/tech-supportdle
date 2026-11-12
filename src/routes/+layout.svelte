<script lang="ts">
	import { resolve } from '$app/paths';
	import '../app.css';
	let { children } = $props();
</script>

<div class="shell">
	{@render children()}
	<footer>
		Questions extracted from the Odoo 19.0 Community source code. New set every day at 00:00 UTC.
		· <a href={resolve('/about')}>How it works</a>
	</footer>
</div>

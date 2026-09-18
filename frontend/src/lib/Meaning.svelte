<script lang="ts">
	import { COPY } from './copy';
	let { children } = $props();
</script>

<details class="meaning">
	<summary>{COPY.meaning}</summary>
	<div class="meaning-body">{@render children()}</div>
</details>

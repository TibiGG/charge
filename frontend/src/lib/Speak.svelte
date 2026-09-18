<script lang="ts">
	import { COPY } from './copy';
	import Icon from './Icon.svelte';
	let { text }: { text: string } = $props();
	let speaking = $state(false);

	function toggle() {
		const s = window.speechSynthesis;
		if (!s) return;
		if (speaking) { s.cancel(); speaking = false; return; }
		s.cancel();
		const u = new SpeechSynthesisUtterance(text);
		u.lang = 'en-GB';
		u.rate = 0.9;
		u.onend = () => (speaking = false);
		u.onerror = () => (speaking = false);
		speaking = true;
		s.speak(u);
	}
</script>

<button class="speak" onclick={toggle} aria-pressed={speaking}>
	<Icon name={speaking ? 'stop' : 'speaker'} size={22} />
	{speaking ? COPY.stop : COPY.readAloud}
</button>

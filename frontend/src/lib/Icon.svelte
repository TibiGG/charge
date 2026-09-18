<script lang="ts">
	let { name, size = 32 }: { name: string; size?: number } = $props();
	const paths: Record<string, string> = {
		// dumbbell
		strength: 'M6 9v6M18 9v6M3 11v2M21 11v2M6 12h12',
		// heart
		cardio: 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z',
		// lightning
		peak: 'M13 3 5 14h6l-1 7 8-11h-6l1-7z',
		// person on one foot
		balance: 'M12 5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM12 7v7M7 10h10M12 14l-1 7M12 14l4 3',
		// wave / stretch
		mobility: 'M3 15c3-6 6-6 9 0s6 6 9 0M3 9c3-6 6-6 9 0',
		speaker: 'M4 9v6h4l5 4V5L8 9H4zM16 8a5 5 0 0 1 0 8M18.5 5.5a8.5 8.5 0 0 1 0 13',
		stop: 'M7 7h10v10H7z',
		calendar: 'M4 6h16v14H4zM4 10h16M8 3v5M16 3v5',
		phone: 'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z',
		watch: 'M8 3h8l1 4v10l-1 4H8l-1-4V7zM7 7h10v10H7z',
		gym: 'M6 9v6M18 9v6M3 11v2M21 11v2M6 12h12M4 20h16',
		home: 'M3 11l9-7 9 7M5 10v10h14V10M10 20v-6h4v6',
		none: 'M12 5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM12 7v6M8 21l4-8 4 8M7 10h10',
		morning: 'M12 3v2M5.6 5.6l1.4 1.4M3 12h2M19 12h2M17 7l1.4-1.4M7 16a5 5 0 0 1 10 0M3 19h18',
		afternoon: 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
		evening: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z',
		info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5v.5'
	};
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
	stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
	<path d={paths[name] ?? paths.info} />
</svg>

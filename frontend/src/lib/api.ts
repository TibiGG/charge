const BASE = import.meta.env.VITE_API_BASE ?? '';

export type Timed<T> = T & { clientMs: number };

async function timed<T>(path: string, init?: RequestInit): Promise<Timed<T>> {
	const t = performance.now();
	const res = await fetch(`${BASE}${path}`, init);
	if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
	const body = (await res.json()) as T;
	return { ...body, clientMs: Math.round(performance.now() - t) };
}

export const api = {
	personas: () => timed<any>('/api/personas'),
	batteries: (p: string) => timed<any>(`/api/batteries/${p}`),
	today: (p: string) => timed<any>(`/api/today/${p}`),
	sources: () => timed<any>('/api/sources'),
	ask: (text: string, persona: string) =>
		timed<any>('/api/ask', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ text, persona })
		}),
	uploadHealth: (file: File) => {
		const fd = new FormData();
		fd.append('file', file);
		return timed<any>('/api/ingest/apple-health', { method: 'POST', body: fd });
	}
};

export function getPersona(): string {
	if (typeof window === 'undefined') return 'margaret';
	const q = new URLSearchParams(location.search).get('p');
	if (q) {
		try { localStorage.setItem('persona', q); } catch {}
		return q;
	}
	try { return localStorage.getItem('persona') ?? 'margaret'; } catch { return 'margaret'; }
}

export function setPersona(p: string) {
	try { localStorage.setItem('persona', p); } catch {}
}

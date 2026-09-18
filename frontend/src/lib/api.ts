import { PUBLIC_API_BASE } from '$env/static/public';

// Empty locally: Vite proxies /api to :8000. On Vercel: the Cloud Run URL.
const BASE = (PUBLIC_API_BASE ?? '').replace(/\/$/, '');

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
	today: (p: string, q: { at?: string; equipment?: string; override_sleep?: boolean; taste?: Taste } = {}) => {
		const qs = new URLSearchParams();
		if (q.at) qs.set('at', q.at);
		if (q.equipment) qs.set('equipment', q.equipment);
		if (q.override_sleep) qs.set('override_sleep', 'true');
		const kinds = (v: Vote) => Object.keys(q.taste ?? {}).filter((k) => q.taste![k] === v).join(',');
		if (kinds('more')) qs.set('more', kinds('more'));
		if (kinds('less')) qs.set('less', kinds('less'));
		return timed<any>(`/api/today/${p}?${qs}`);
	},
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

export function getEquipment(p: string): string | null {
	try { return localStorage.getItem(`equipment:${p}`); } catch { return null; }
}

export function setEquipment(p: string, v: string) {
	try { localStorage.setItem(`equipment:${p}`, v); } catch {}
}

/** Viewer's local time, or ?at=HH:MM to pin it for the demo. */
export function getNow(): string {
	const q = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('at') : null;
	if (q && /^([01]\d|2[0-3]):[0-5]\d$/.test(q)) return q;
	const d = new Date();
	return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** "More / less like this" votes, per activity id. Kept in this browser only. */
export type Vote = 'more' | 'less';
export type Taste = Record<string, Vote>;

export function getTaste(p: string): Taste {
	try { return JSON.parse(localStorage.getItem(`taste:${p}`) ?? '{}'); } catch { return {}; }
}

export function setVote(p: string, kind: string, v: Vote | null): Taste {
	const t = getTaste(p);
	if (v) t[kind] = v; else delete t[kind];
	try { localStorage.setItem(`taste:${p}`, JSON.stringify(t)); } catch {}
	return t;
}

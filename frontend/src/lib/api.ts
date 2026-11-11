import { env } from '$env/dynamic/public';
import { isDemo, signedIn, token } from './auth';
import { getHealth, type Health } from './health';
import { localKey } from './vault';

// Empty locally: Vite proxies /api to :8000. Deployed: the API's own URL.
const BASE = (env.PUBLIC_API_BASE ?? '').replace(/\/$/, '');

/** A signed-in person is 'me'; the demo's made-up people have their own ids. */
export const ME = 'me';

export type Timed<T> = T & { clientMs: number };

async function timed<T>(path: string, init: RequestInit = {}): Promise<Timed<T>> {
	const t = performance.now();
	const headers = new Headers(init.headers);
	if (path.startsWith('/api/me')) {
		headers.set('Authorization', token());
		// Their key opens their sealed vault for this one request. Header only: never a URL.
		const k = localKey();
		if (k) headers.set('X-Charge-Key', k);
	}
	const res = await fetch(`${BASE}${path}`, { ...init, headers });
	if (res.status === 423 && typeof location !== 'undefined' && location.pathname !== '/unlock') {
		location.href = '/unlock';
	}
	if (!res.ok) {
		let detail = '';
		try { detail = (await res.json()).detail ?? ''; } catch {}
		throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status, detail });
	}
	const body = (await res.json()) as T;
	return { ...body, clientMs: Math.round(performance.now() - t) };
}

const json = (method: string, body: unknown): RequestInit => ({
	method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body)
});

/** The viewer's local date, YYYY-MM-DD. */
export function localDate(): string {
	const d = new Date();
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function pinnedAt(): string | null {
	const q = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('at') : null;
	return q && /^([01]\d|2[0-3]):[0-5]\d$/.test(q) ? q : null;
}

export const api = {
	personas: () => timed<any>('/api/personas'),
	batteries: (p: string, extraLogs: ActivityLog[] = []) => p === ME
		? timed<any>('/api/me/batteries', extraLogs.length ? json('POST', { logs: extraLogs }) : {})
		: timed<any>(`/api/batteries/${p}?${activityQs(p, extraLogs)}`),
	activity: (p: string) => timed<any>(p === ME ? '/api/me/activity' : `/api/activity/${p}?${activityQs(p)}`),
	profile: (p: string) => timed<any>(p === ME ? '/api/me/profile' : `/api/profile/${p}`),
	today: (p: string, q: { at?: string; equipment?: string; override_sleep?: boolean; taste?: Taste; profile?: Profile } = {}) => {
		if (p === ME) {
			const qs = new URLSearchParams();
			const at = pinnedAt();
			if (at) qs.set('at', at);
			if (q.override_sleep) qs.set('override_sleep', 'true');
			return timed<any>(`/api/me/today?${qs}`); // their health check is in their vault
		}
		const qs = new URLSearchParams();
		const skipped = getSkips(p);
		if (skipped.length) qs.set('skip', skipped.join(','));
		if (q.at) qs.set('at', q.at);
		if (q.equipment) qs.set('equipment', q.equipment);
		if (q.override_sleep) qs.set('override_sleep', 'true');
		const kinds = (v: Vote) => Object.keys(q.taste ?? {}).filter((k) => q.taste![k] === v).join(',');
		if (kinds('more')) qs.set('more', kinds('more'));
		if (kinds('less')) qs.set('less', kinds('less'));
		if (q.profile?.kit) qs.set('kit', JSON.stringify(q.profile.kit));
		if (q.profile?.age) qs.set('age', String(q.profile.age));
		if (q.profile?.habits) qs.set('habits', q.profile.habits.join(','));
		for (const [k, v] of activityQs(p)) qs.set(k, v);
		// The demo's health check goes in the body, never the URL: URLs end up in logs.
		return timed<any>(`/api/today/${p}?${qs}`, json('POST', { health: getHealth(p) }));
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
	},

	// ---- signed-in only ----
	me: () => timed<any>('/api/me'),
	consent: (version: string) => timed<any>('/api/me/consent', json('POST', { version, scopes: { health_data: true, recommendations: true } })),
	saveProfile: (body: Record<string, unknown>) => timed<any>('/api/me/profile', json('PUT', body)),
	importHealth: (file: File) => {
		const fd = new FormData();
		fd.append('file', file);
		return timed<any>('/api/me/import', { method: 'POST', body: fd });
	},
	importStatus: (job: string) => timed<any>(`/api/me/import/${job}`),
	syncToken: () => timed<any>('/api/me/sync-token', { method: 'POST' }),
	exportData: () => timed<any>('/api/me/export'),
	health: () => timed<{ health: Health | null }>('/api/me/health'),
	saveHealth: (health: Health | null) => timed<any>('/api/me/health', json('PUT', { health })),
	learned: () => timed<{ ask: Ask[]; learned: Learned[] }>('/api/me/learned'),
	answer: (id: string, value: string) => timed<{ ask: Ask[]; learned: Learned[] }>('/api/me/answers', json('POST', { id, value })),
	feedback: (activity_id: string, signal: 'planned' | 'not_today') =>
		timed<any>('/api/me/feedback', json('POST', { activity_id, signal })),
	deleteAccount: () => timed<any>('/api/me', { method: 'DELETE' }),
	syncUrl: () => `${BASE || location.origin}/api/sync/workouts`
};

/** A question Charge asks in place of a longer form (backend/app/learn.py). */
export type Ask = { id: string; text: string; options: { value: string; label: string }[];
	source_id: string | null; source: any; note: string | null };
/** Something Charge picked up from what they do. Undo = answer(id, 'yes'). */
export type Learned = { id: string; text: string };

// ---- Writes: a signed-in person's go to the server; the demo's stay in this browser. ----

export async function addLog(p: string, log: ActivityLog) {
	if (p === ME) {
		const { id: _id, ...body } = log;
		await timed('/api/me/logs', json('POST', body));
	} else setLogs(p, [...getLogs(p), log]);
}

export async function removeLog(p: string, id: string) {
	if (p === ME) await timed(`/api/me/logs/${id}`, { method: 'DELETE' });
	else setLogs(p, getLogs(p).filter((l) => l.id !== id));
}

export async function vote(p: string, kind: string, v: Vote | null, current: Taste): Promise<Taste> {
	if (p !== ME) return setVote(p, kind, v);
	await timed('/api/me/votes', json('POST', { activity_id: kind, vote: v }));
	const t = { ...current };
	if (v) t[kind] = v; else delete t[kind];
	return t;
}

/** "Something else": this idea is off the table until tomorrow. */
export async function skip(p: string, id: string | null) {
	if (p === ME) {
		if (id) await timed('/api/me/skip', json('POST', { activity_id: id }));
		return;
	}
	const k = `skips:${p}:${localDate()}`;
	try { localStorage.setItem(k, JSON.stringify(id ? [...getSkips(p), id] : [])); } catch {}
}

export function getSkips(p: string): string[] {
	try { return JSON.parse(localStorage.getItem(`skips:${p}:${localDate()}`) ?? '[]'); } catch { return []; }
}

export async function saveProfile(p: string, v: Profile & Record<string, unknown>) {
	if (p === ME) await api.saveProfile(v);
	else setProfile(p, v);
}

export function getPersona(): string {
	if (typeof window === 'undefined') return 'margaret';
	if (!isDemo() && signedIn()) return ME;
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

/** The User tab: what they told us. Kept in this browser; sent with every plan. */
export type GymWindow = { from: string; to: string; label?: string };
export type Kit = { home: string[]; gym: null | { items: string[]; windows: GymWindow[] } };
export type Profile = { age?: number; habits?: string[]; kit?: Kit };

export const KIT_PRESETS: Record<string, Kit> = {
	none: { home: ['chair'], gym: null },
	home: { home: ['chair', 'mat', 'dumbbells', 'band'], gym: null },
	gym: { home: ['chair'], gym: { items: ['machines', 'dumbbells', 'bike', 'mat', 'band', 'pool'], windows: [{ from: '06:00', to: '22:00', label: 'Any time' }] } }
};

export function tierOf(k: Kit): string {
	return k.gym ? 'gym' : k.home.some((i) => i !== 'chair') ? 'home' : 'none';
}

export function getProfile(p: string): Profile {
	try { return JSON.parse(localStorage.getItem(`profile:${p}`) ?? '{}'); } catch { return {}; }
}

export function setProfile(p: string, v: Profile) {
	try { localStorage.setItem(`profile:${p}`, JSON.stringify(v)); } catch {}
}

/** Activity tab: their own logs + whether they have synced the watch. Kept in this browser. */
export type ActivityLog = { id: string; type: string; start: string; duration_min: number;
	effort: 'easy' | 'moderate' | 'hard'; counts: string[]; note?: string };

export function getLogs(p: string): ActivityLog[] {
	try { return JSON.parse(localStorage.getItem(`logs:${p}`) ?? '[]'); } catch { return []; }
}
export function setLogs(p: string, v: ActivityLog[]) {
	try { localStorage.setItem(`logs:${p}`, JSON.stringify(v)); } catch {}
}
export function getSynced(p: string): boolean {
	try { return localStorage.getItem(`synced:${p}`) === '1'; } catch { return false; }
}
export function setSynced(p: string, v: boolean) {
	try { v ? localStorage.setItem(`synced:${p}`, '1') : localStorage.removeItem(`synced:${p}`); } catch {}
}

function activityQs(p: string, extra: ActivityLog[] = []): URLSearchParams {
	const qs = new URLSearchParams();
	if (typeof window === 'undefined') return qs;
	const logs = [...getLogs(p), ...extra];
	if (logs.length) qs.set('logs', JSON.stringify(logs));
	if (getSynced(p)) qs.set('synced', 'true');
	return qs;
}

import { env } from '$env/dynamic/public';
import { pb, token } from './auth';

/** Each account's key. It's made here, kept here, and sent only in the X-Charge-Key header,
 * so the server can open the person's sealed vault for one request (backend/app/vault.py).
 *
 * The server also keeps two LOCKED copies, so a new device can get the key back:
 *   - locked by their password (PBKDF2-SHA256, 600k rounds), for email sign-ins;
 *   - locked by a recovery key we show them once, for Google/Apple and password resets.
 * The server never sees their password (PocketBase checks that) or their recovery key. */

const BASE = (env.PUBLIC_API_BASE ?? '').replace(/\/$/, '');
const PW_ITER = 600_000;
const RK_ITER = 100_000; // the recovery key is already 100 random bits, so fewer rounds are fine
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'; // Crockford base32: no I, L, O or U

type Bytes = Uint8Array<ArrayBuffer>;
const b64u = (b: Uint8Array) => btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const unb64u = (s: string): Bytes => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));

function slot(): string | null {
	const id = pb.authStore.record?.id;
	return id ? `vault:${id}` : null;
}

/** This device's copy of the key, for the signed-in account. */
export function localKey(): string | null {
	const k = slot();
	try { return k ? localStorage.getItem(k) : null; } catch { return null; }
}
function keep(key: Bytes) {
	const k = slot();
	try { if (k) localStorage.setItem(k, b64u(key)); } catch {}
}
export function forgetKey() {
	const k = slot();
	try { if (k) localStorage.removeItem(k); } catch {}
}

export function newRecoveryKey(): string {
	const r = crypto.getRandomValues(new Uint8Array(20));
	const chars = Array.from(r, (x) => ALPHABET[x % 32]).join(''); // 256 % 32 == 0, so no bias
	return chars.match(/.{4}/g)!.join('-');
}
/** Forgiving: any case, spaces or dashes, and O/I/L typed for 0/1/1. */
export function tidyRecoveryKey(s: string): string {
	return s.toUpperCase().replace(/[\s-]/g, '').replace(/O/g, '0').replace(/[IL]/g, '1');
}

async function lockFor(secret: string, salt: Bytes, iter: number): Promise<CryptoKey> {
	const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), 'PBKDF2', false, ['deriveKey']);
	return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations: iter }, base,
		{ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
}

async function lock(key: Bytes, secret: string, iter: number) {
	const salt = crypto.getRandomValues(new Uint8Array(16));
	const iv = crypto.getRandomValues(new Uint8Array(12));
	const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await lockFor(secret, salt, iter), key));
	const out = new Uint8Array(12 + ct.length);
	out.set(iv); out.set(ct, 12);
	return { wrap: b64u(out), kdf: { salt: b64u(salt), iter } };
}

async function unlock(wrap: string, secret: string, kdf: { salt: string; iter: number }): Promise<Bytes | null> {
	try {
		const raw = unb64u(wrap);
		const k = await lockFor(secret, unb64u(kdf.salt), kdf.iter);
		const key = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: raw.slice(0, 12) }, k, raw.slice(12)));
		return key.length === 32 ? key : null;
	} catch { return null; }
}

type Locks = { exists: boolean; kdf?: { pw?: { salt: string; iter: number }; rk?: { salt: string; iter: number } };
	wrap_pw?: string; wrap_rk?: string };

async function call(method: string, path: string, body?: unknown, key?: Bytes) {
	const headers: Record<string, string> = { Authorization: token() };
	if (body) headers['content-type'] = 'application/json';
	if (key) headers['X-Charge-Key'] = b64u(key);
	const res = await fetch(`${BASE}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
	if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
	return res.json();
}

/** Handed from sign-in to the next page, in memory only (never stored). */
export const pending: { recovery?: string; password?: string } = {};

async function setUp(password?: string): Promise<string> {
	const key = crypto.getRandomValues(new Uint8Array(32));
	const recovery = newRecoveryKey();
	const rk = await lock(key, tidyRecoveryKey(recovery), RK_ITER);
	const pw = password ? await lock(key, password, PW_ITER) : null;
	await call('POST', '/api/me/vault', {
		wrap_rk: rk.wrap, wrap_pw: pw?.wrap ?? '', kdf: { rk: rk.kdf, ...(pw ? { pw: pw.kdf } : {}) }
	}, key);
	keep(key);
	return recovery;
}

/** Right after signing in. 'new' = we made their key (show pending.recovery);
 * 'open' = this device has it now; 'locked' = they need their recovery key (/unlock). */
export async function afterSignIn(password?: string): Promise<'new' | 'open' | 'locked'> {
	const v: Locks = await call('GET', '/api/me/vault');
	if (!v.exists) {
		pending.recovery = await setUp(password);
		return 'new';
	}
	if (localKey()) return 'open';
	if (password && v.wrap_pw && v.kdf?.pw) {
		const key = await unlock(v.wrap_pw, password, v.kdf.pw);
		if (key) { keep(key); return 'open'; }
	}
	pending.password = password; // a reset password: lock the key with the new one once they're in
	return 'locked';
}

/** First visit with no vault at all (e.g. an account from before vaults, signed in with Google). */
export async function setUpNow(): Promise<void> {
	pending.recovery = await setUp(pending.password);
	pending.password = undefined;
}

export async function unlockWithRecovery(recovery: string): Promise<boolean> {
	const v: Locks = await call('GET', '/api/me/vault');
	if (!v.exists || !v.wrap_rk || !v.kdf?.rk) return false;
	const key = await unlock(v.wrap_rk, tidyRecoveryKey(recovery), v.kdf.rk);
	if (!key) return false;
	keep(key);
	if (pending.password) {
		const pw = await lock(key, pending.password, PW_ITER);
		await call('PUT', '/api/me/vault', { wrap_pw: pw.wrap, kdf: { ...v.kdf, pw: pw.kdf } }, key);
		pending.password = undefined;
	}
	return true;
}

/** A new recovery key for the same key. The old recovery key stops working. */
export async function replaceRecoveryKey(): Promise<string> {
	const k = localKey();
	if (!k) throw new Error('locked');
	const key = unb64u(k);
	const v: Locks = await call('GET', '/api/me/vault');
	const recovery = newRecoveryKey();
	const rk = await lock(key, tidyRecoveryKey(recovery), RK_ITER);
	await call('PUT', '/api/me/vault', { wrap_rk: rk.wrap, kdf: { ...v.kdf, rk: rk.kdf } }, key);
	return recovery;
}

/** Lost both password and recovery key: the old vault can't be opened by anyone, so it goes. */
export async function startAgain(): Promise<void> {
	await call('POST', '/api/me/vault/reset', { confirm: 'START AGAIN' });
	forgetKey();
	await setUpNow();
}

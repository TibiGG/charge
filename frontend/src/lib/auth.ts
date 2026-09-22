import PocketBase from 'pocketbase';
import { env } from '$env/dynamic/public';

// Accounts live in PocketBase. The Charge API checks the same token on every /api/me call.
export const pb = new PocketBase((env.PUBLIC_PB_URL ?? 'http://127.0.0.1:8090').replace(/\/$/, ''));
pb.autoCancellation(false);

export const accountsEnabled = () => !!env.PUBLIC_PB_URL;

export function signedIn(): boolean {
	return pb.authStore.isValid && pb.authStore.record?.collectionName === 'users';
}

export function token(): string {
	return pb.authStore.token;
}

export function signOut() {
	pb.authStore.clear();
	setDemo(false);
}

/** The demo (made-up personas) is a separate mode, so it never mixes with a real account. */
export function isDemo(): boolean {
	if (typeof window === 'undefined') return false;
	if (new URLSearchParams(location.search).has('p')) setDemo(true);
	try { return localStorage.getItem('mode') === 'demo'; } catch { return false; }
}

export function setDemo(on: boolean) {
	try { on ? localStorage.setItem('mode', 'demo') : localStorage.removeItem('mode'); } catch {}
}

export async function refresh(): Promise<boolean> {
	if (!pb.authStore.isValid) return false;
	try {
		await pb.collection('users').authRefresh();
		return true;
	} catch {
		pb.authStore.clear();
		return false;
	}
}

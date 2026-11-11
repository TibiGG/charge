/** The Health check. A signed-in person's is saved in their sealed vault (api.health /
 * api.saveHealth), which only their own key opens. The demo's made-up people keep theirs in
 * this browser (below); it goes in the body of each plan request, never in a URL. */
export type Screen = Partial<Record<(typeof SCREEN)[number], boolean>>;
export type Health = {
	screen: Screen;
	cleared: boolean;
	conditions: string[];
	menopause: '' | 'pre' | 'peri' | 'post';
	easy_joints: boolean;
	report: null | { bones: string; heart: string; variants: string[] };
	updated?: string;
};

// Same order and meaning as backend/app/health.py. The words are in copy.ts.
export const SCREEN = ['heart', 'chest_pain', 'dizzy', 'other_condition', 'medicines', 'joints', 'supervised'] as const;
const SYMPTOMS = ['chest_pain', 'dizzy', 'supervised'];
export const CONDITIONS = ['thin_bones', 'high_bp', 'type2_diabetes', 'pregnant', 'fall'] as const;

export const EMPTY: Health = { screen: {}, cleared: false, conditions: [], menopause: '', easy_joints: false, report: null };

const key = (p: string) => `health:${p}`;

export function getHealth(p: string): Health | null {
	try {
		const raw = localStorage.getItem(key(p));
		return raw ? { ...EMPTY, ...JSON.parse(raw) } : null;
	} catch { return null; }
}

export function setHealth(p: string, h: Health) {
	try { localStorage.setItem(key(p), JSON.stringify({ ...h, updated: new Date().toISOString().slice(0, 10) })); } catch {}
}

export function clearHealth(p: string) {
	try { localStorage.removeItem(key(p)); } catch {}
}

/** Mirrors readiness() in backend/app/health.py, so the form can say what will happen. */
export function readiness(h: Health | null): 'ok' | 'gentle' | 'check' {
	if (!h || h.cleared) return 'ok';
	const yes = SCREEN.filter((k) => h.screen[k]);
	if (yes.some((k) => SYMPTOMS.includes(k))) return 'check';
	return yes.length || h.conditions.includes('pregnant') ? 'gentle' : 'ok';
}

export function anyYes(h: Health): boolean {
	return SCREEN.some((k) => h.screen[k]) || h.conditions.includes('pregnant');
}

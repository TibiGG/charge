// Every piece of UI copy lives here so tests/test_constraints.py can check
// reading level and banned words. Short words. One idea per sentence.

export const COPY = {
	appName: 'Charge',
	tagline: 'Your charge is set by your emptiest battery.',
	noStreak: "There's no streak to break here. Each battery looks at the last 7 days.",
	primaryToday: 'What should I do today?',
	chargeLabel: 'Your charge',
	chargeSetBy: 'Right now, your charge is set by',
	tapVial: 'Tap a battery to learn more.',

	bands: {
		topped_up: 'Topped up',
		ticking_over: 'Ticking over',
		room_to_grow: 'Room to grow'
	},

	batteries: {
		strength: {
			label: 'Strength',
			what: 'This is muscle work. It keeps your muscles and bones strong.',
			examples: 'Weights, squats, or carrying heavy bags all count.'
		},
		cardio: {
			label: 'Cardio endurance',
			what: 'This is activity that warms you up and makes you breathe a bit faster.',
			examples: 'A brisk walk, a bike ride or a swim all count.'
		},
		peak: {
			label: 'HIIT / VO2max',
			what: 'This is hard effort. You can only say a few words at a time.',
			examples: 'Running, fast cycling or a hard class all count.'
		},
		balance: {
			label: 'Balance & stability',
			what: 'This is balance work. It helps you stay steady on your feet.',
			examples: 'Tai chi, standing on one leg, or heel-to-toe walking all count.'
		},
		mobility: {
			label: 'Flexibility & mobility',
			what: 'This is stretching. It helps you move with ease.',
			examples: 'Yoga, pilates or a gentle stretch all count.'
		}
	},

	sheet: {
		whatThisIs: 'What this is',
		whereYouAre: 'Where you are',
		whatPeopleAimFor: 'What people aim for',
		lastWeek: 'Last week you did',
		weakSource:
			'This aim is our weakest one. It comes from a fitness plan, not a health body. We show it so you can judge it.',
		close: 'Close'
	},

	today: {
		title: 'Your one thing for today',
		when: 'When',
		howSure: 'How sure are we?',
		addToCalendar: 'Put it in my calendar',
		added: 'Done. It is in your calendar.',
		notToday: 'Not today',
		notTodayDone: "That's fine. Rest days count too.",
		why: 'Why this?',
		whyTitle: 'Why we suggested this',
		proofTitle: 'The exact steps our checker took',
		proofIntro: 'Each line is one way the rules lead to this idea. The number is how much it adds.',
		video: 'Watch and follow along',
		seated: 'Prefer to sit? Try this one.',
		quick: 'We used our quick answer here.',
		otherIdeas: 'Other ideas',
		loading: 'Working out your one thing…',
		noWatch: 'Connect your watch first. Then we can suggest one thing for you.',
		productChoice: 'Why a version of something you already do?',
		back: 'Back to my batteries'
	},

	ask: {
		title: 'Ask',
		intro: 'Ask about your batteries, your report, or what to do.',
		placeholder: 'Type your question here',
		send: 'Ask',
		examplesTitle: 'Try one of these',
		examples: [
			'How can I get stronger?',
			'What does my genome report mean?',
			'I have chest pain when I run',
			'Should I stop taking my statins?'
		],
		refusalTitle: "I can't help with that one.",
		refusalBody: "That's a question for a person, not an app.",
		refusalCta: 'A Bupa health adviser can help.',
		refusalButton: 'Talk to someone now',
		safety: 'If this is an emergency, call 999. If you need urgent advice, call 111.'
	},

	onboarding: {
		title: 'Connect your watch',
		body: 'We use your Apple Watch to fill your batteries. Nothing is shared without your say.',
		step1: 'On your iPhone, open the Health app.',
		step2: 'Tap your picture, then "Export All Health Data".',
		step3: 'Send the file here.',
		button: 'Choose my Health file',
		working: 'Reading your file…'
	},

	dayparts: {
		morning: 'Morning',
		afternoon: 'Afternoon',
		evening: 'Evening',
		now: 'Now',
		later: 'Later',
		earlier: 'Earlier',
		lateNight: "It's late. Rest well. Here's what tomorrow could look like."
	},

	equipment: {
		title: 'What do you have?',
		hint: 'You can change this any time.',
		gym: 'I go to a gym',
		home: 'I have some kit at home',
		none: 'Just me and some space'
	},

	day: {
		title: 'Your day',
		intro: 'One idea for each part of the day. Only the one for now has a button.',
		gotIt: 'Got it',
		whyContext: 'Why now, and why this one',
		ourChoice: 'Our choice, not a health claim',
		mixed: 'Mixed evidence',
		ranking: 'What else we looked at',
		steps: 'How to do it',
		harderChosen: 'You picked the harder one. That is your call.',
		backToGentle: 'Go back to the gentler one',
		loading: 'Working out your day…',
		noise: 'Noise',
		canSit: 'You can sit for this.',
		tryAgain: 'Try again',
		whyOurCall: 'Why is this our call?',
		look: 'Take a look',
		lookEarlier: 'This was the idea for earlier. You can still read it.',
		lookLater: 'This is the plan for later. Its button shows up then.',
		moreLike: 'More like this',
		lessLike: 'Less like this',
		votedMore: "Thanks. We'll show you more like this.",
		votedLess: "Thanks. We'll show you less like this.",
		voteCleared: "Okay. We've undone that.",
		logicTitle: 'Check the logic',
		logicIntro: 'This is the exact logic program that made this pick. You can check each step.',
		logicQuery: 'What we asked',
		logicScore: 'Score',
		logicProofs: 'Each way the rules reach this pick',
		logicRules: 'The rules it used',
		logicFacts: 'What we know, as facts',
		seatedWhy: 'You picked the seated one. It works the same batteries, so the reasons below still hold.'
	},

	welcome: {
		title: 'Welcome to Charge',
		intro: 'Two quick steps. Then we can suggest one thing for each part of your day.',
		step1: 'Step 1: Your account',
		bupa: 'Sign in with Bupa',
		google: 'Continue with Google',
		email: 'Use my email',
		emailLabel: 'Your email',
		emailGo: 'Send me a sign-in link',
		signingIn: 'Signing you in…',
		signedIn: "You're in.",
		signedInWith: 'Signed in with',
		step2: 'Step 2: Your watch or tracker',
		step2Intro: 'We use it to fill your batteries. Nothing is shared without your say.',
		connect: 'Connect',
		connecting: 'Connecting…',
		connected: 'Connected.',
		found: 'We found 14 days of workouts and sleep.',
		step3: "You're all set",
		kit: 'Tell us what kit you have',
		go: 'See my batteries',
		startOver: 'Start again',
		demoNote: 'This is a prototype. Sign-in and connecting are simulated. Nothing is sent.'
	},

	activity: {
		title: 'Your activity',
		intro: 'Everything that fills your batteries. It comes from your watch, or you can add it.',
		sync: 'Sync my watch',
		syncing: 'Syncing…',
		synced: 'Your watch is up to date.',
		found: 'new from your watch',
		unsync: 'Undo the sync',
		add: 'Add something you did',
		what: 'What did you do?',
		when: 'When',
		howLong: 'How long, in minutes',
		effort: 'How hard was it?',
		easy: 'Easy',
		moderate: 'Could still talk',
		hard: 'Could only say a few words',
		counts: 'Which batteries should it fill?',
		countsHint: 'We ticked what this usually fills. You know best, so change it if you like.',
		note: 'Note (if you like)',
		change: 'What this will change',
		noChange: 'This will not change your batteries. Tick at least one.',
		save: 'Add it',
		saved: 'Added. Your batteries now include it.',
		seeBatteries: 'See my batteries',
		list: 'This week and last week',
		yours: 'Added by you',
		noneYet: 'Nothing added yet.',
		fromWatch: 'Watch',
		fromYou: 'You added this',
		fills: 'Fills',
		nothing: 'Fills none',
		remove: 'Remove',
		olderThanWeek: 'Last week'
	},

	user: {
		title: 'About you',
		intro: 'This is what we use to pick your ideas. Change anything. It stays on this device.',
		fineTune: 'Tell us exactly what kit you have',
		you: 'You',
		name: 'Name',
		age: 'Age',
		habits: 'Things you already do',
		homeKit: 'Kit at home',
		homeHint: 'Tick what you have. If you have none of it, leave it all blank. We will only suggest things you can do.',
		noKit: 'I have no kit at all',
		gym: 'A gym',
		gymToggle: 'I can use a gym',
		gymKit: 'What the gym has',
		when: 'When can you get there?',
		whenHint: 'Add each time you could go. For example, before work, or a lunch break if the gym is near work.',
		from: 'From',
		to: 'To',
		label: 'Note',
		add: 'Add a time',
		remove: 'Remove',
		quick: 'Quick add',
		save: 'Save',
		saved: 'Saved. Your day now uses this.',
		reset: 'Go back to what we knew',
		noWindows: 'Add at least one time, or we will not suggest the gym.',
		seeDay: 'See my day'
	},

	offline: "We can't reach Charge right now. Please try again in a moment.",

	of: 'of',
	fromYou: 'new',
	includesYours: 'This includes what you added.',
	ownLogs: 'This includes things you added or synced.',
	seeActivity: 'See your activity',

	meaning: 'What does this mean?',
	readAloud: 'Read aloud',
	stop: 'Stop',
	sourcesLabel: 'Where this comes from',
	grades: {
		clinical_guideline: 'Clinical guideline',
		peer_reviewed: 'Peer-reviewed',
		commercial_protocol: 'Commercial protocol'
	},
	genetic: "This nudges your starting point. It doesn't tell you what will happen.",
	latency: 'Time to answer',
	nav: { welcome: 'Welcome', home: 'Batteries', today: 'Today', ask: 'Ask', activity: 'Activity', user: 'User' }
} as const;

export type BatteryId = keyof typeof COPY.batteries;

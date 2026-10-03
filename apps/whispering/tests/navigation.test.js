import { describe, expect, mock, test } from 'bun:test';
import { parse } from 'svelte/compiler';

// Exercise the actual navigation callback rather than duplicating its guard.
const source = await Bun.file(
	new URL('../src/routes/+layout.svelte', import.meta.url),
).text();
const ast = parse(source, { modern: true });
const registration = ast.instance.content.body.find(
	(node) =>
		node.type === 'ExpressionStatement' &&
		node.expression.type === 'CallExpression' &&
		node.expression.callee.name === 'onNavigate',
);
const callback = registration.expression.arguments[0];
const createNavigation = new Function(
	'os',
	'tauri',
	'window',
	'document',
	`return (${source.slice(callback.start, callback.end)});`,
);

describe('navigation view transitions', () => {
	test('Linux desktop navigates without entering the crashing renderer', () => {
		const startViewTransition = mock(() => {
			throw new Error('WebKitGTK accelerated rendering must not be entered');
		});
		const navigate = createNavigation({ isLinux: true }, {}, {}, {
			startViewTransition,
		});
		expect(navigate({ complete: Promise.resolve() })).toBeUndefined();
		expect(startViewTransition).not.toHaveBeenCalled();
	});

	for (const [platform, linux, desktop] of [
		['Linux browser', true, false],
		['other desktop platforms', false, true],
		['other browsers', false, false],
	]) {
		test(`${platform} retains supported view transitions`, async () => {
			const startViewTransition = mock((update) => update());
			const navigate = createNavigation(
				{ isLinux: linux },
				desktop ? {} : null,
				{ matchMedia: () => ({ matches: false }) },
				{ startViewTransition },
			);
			await navigate({ complete: Promise.resolve() });
			expect(startViewTransition).toHaveBeenCalledTimes(1);
		});
	}

	test('reduced motion still skips transitions on other platforms', () => {
		const startViewTransition = mock(() => {});
		const navigate = createNavigation(
			{ isLinux: false },
			null,
			{ matchMedia: () => ({ matches: true }) },
			{ startViewTransition },
		);
		expect(navigate({ complete: Promise.resolve() })).toBeUndefined();
		expect(startViewTransition).not.toHaveBeenCalled();
	});

	test('engines without the API navigate normally', () => {
		const navigate = createNavigation({ isLinux: false }, null, {}, {});
		expect(navigate({ complete: Promise.resolve() })).toBeUndefined();
	});
});

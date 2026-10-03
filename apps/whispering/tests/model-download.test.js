import { expect, mock, test } from 'bun:test';
import { parse } from 'svelte/compiler';
import { isModelFileSizeValid } from '../src/lib/services/isomorphic/transcription/local/types';

const source = await Bun.file(new URL('../src/lib/components/settings/LocalModelDownloadCard.svelte', import.meta.url)).text();
const ast = parse(source, { modern: true });
const transpiler = new Bun.Transpiler({ loader: 'ts' });
function find(node, predicate) {
	if (!node || typeof node !== 'object') return;
	if (predicate(node)) return node;
	for (const value of Object.values(node)) {
		const match = Array.isArray(value)
			? value.map((child) => find(child, predicate)).find(Boolean)
			: find(value, predicate);
		if (match) return match;
	}
}
const download = find(ast.instance.content, (node) => node.type === 'VariableDeclarator' && node.id.name === 'downloadFileContent').init;
const code = transpiler.transformSync(`const download = ${source.slice(download.start, download.end)};`);

function downloader(body, contentLength, wrongDiskSize = false) {
	const files = new Map([['model.bin', new Uint8Array([9])]]);
	const rename = mock(async (from, to) => { files.set(to, files.get(from)); files.delete(from); });
	const writeFile = async (path, bytes, options) => {
		files.set(path, options?.append ? new Uint8Array([...files.get(path), ...bytes]) : bytes);
	};
	const stat = async (path) => ({ size: files.get(path).length + Number(wrongDiskSize) });
	const remove = async (path) => { files.delete(path); };
	const fetch = async () => new Response(body, { headers: { 'content-length': String(contentLength) } });
	const run = new Function('fetch', 'writeFile', 'stat', 'remove', 'rename', `${code}\nreturn download;`)(fetch, writeFile, stat, remove, rename);
	return { run, files, rename };
}

test('complete download is published atomically', async () => {
	const { run, files, rename } = downloader(new Uint8Array([1, 2, 3, 4]), 4);
	await run('url', 4, 'model.bin', () => {});
	expect([...files.get('model.bin')]).toEqual([1, 2, 3, 4]);
	expect(rename).toHaveBeenCalledTimes(1);
	expect(files.size).toBe(1);
});

for (const [reason, body, declared, wrongSize] of [
	['truncated body', [1, 2], 4, false],
	['oversized body', [1, 2, 3, 4], 2, false],
	['disk size mismatch', [1, 2, 3, 4], 4, true],
]) {
	test(`${reason} preserves the existing model`, async () => {
		const { run, files, rename } = downloader(new Uint8Array(body), declared, wrongSize);
		await expect(run('url', declared, 'model.bin', () => {})).rejects.toThrow('Download size mismatch');
		expect([...files.get('model.bin')]).toEqual([9]);
		expect(rename).not.toHaveBeenCalled();
		expect(files.size).toBe(1);
	});
}

test('model validation rejects the observed oversized Turbo file', () => {
	expect(isModelFileSizeValid(2_541_948_500, 1_624_555_275)).toBe(false);
	expect(isModelFileSizeValid(1_624_555_275, 1_624_555_275)).toBe(true);
	expect(isModelFileSizeValid(1_000, 2_000)).toBe(false);
});

test('download lock survives status changes and blocks concurrent clicks', async () => {
	const node = find(ast.instance.content, (node) => node.type === 'FunctionDeclaration' && node.id.name === 'downloadModel');
	const functionCode = transpiler.transformSync(source.slice(node.start, node.end));
	let finish;
	const tryAsync = mock(() => new Promise((resolve) => { finish = resolve; }));
	const { run, setStatus, locked } = new Function('tryAsync', `let isDownloading = false; let modelState = {}; ${functionCode}\nreturn {run: downloadModel, setStatus: () => {modelState = {type: 'not-downloaded'};}, locked: () => isDownloading};`)(tryAsync);
	const first = run();
	setStatus();
	await run();
	expect(tryAsync).toHaveBeenCalledTimes(1);
	expect(locked()).toBe(true);
	finish();
	await first;
	expect(locked()).toBe(false);
});

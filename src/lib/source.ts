import generated from './data/generated.json';

/** The odoo/odoo commit the pool was generated from; links pin to it so line numbers stay right. */
const COMMIT = (generated as { meta: { commit: string | null; version: string } }).meta;
const REF = COMMIT.commit ?? COMMIT.version;

/**
 * GitHub URL for a question source such as `odoo/addons/sale/models/sale_order.py:120`.
 * Sources are relative to the folder that holds the community checkout, so the leading
 * `odoo/` is the repository itself.
 */
export function sourceUrl(source: string): string {
	const m = /^(.*?)(?::(\d+))?$/.exec(source.trim())!;
	const path = m[1].replace(/^odoo\//, '');
	return `https://github.com/odoo/odoo/blob/${REF}/${path}${m[2] ? `#L${m[2]}` : ''}`;
}

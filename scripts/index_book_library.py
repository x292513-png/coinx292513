"""Index all extracted units locally; OCR keeps provenance, not review approval."""
import json,re,sqlite3
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'data/book-library'
catalog=json.loads((root/'catalog.json').read_text())
overrides={'49a10df7f3bd':'scanned-notes-ocr.jsonl','b62faa00c881':'neely-revised-ocr.jsonl'}
for item in catalog:
    if item['id'] in overrides:
        path=root/'extracted'/item['id']/'units.json'
        original=path.with_name('native-units.json')
        if not original.exists():original.write_bytes(path.read_bytes())
        rows=[json.loads(x) for x in (root/'extracted'/overrides[item['id']]).read_text().splitlines()]
        if len(rows)!=item['units'] or sorted(x['page'] for x in rows)!=list(range(1,item['units']+1)):
            raise ValueError('incomplete_ocr '+item['id'])
        units=[{'locator':f'pdf_page:{r["page"]}','text':r['text'],'method':r['method'],'mean_confidence':r['mean_confidence'],'chars':len(r['text'].strip())} for r in sorted(rows,key=lambda r:r['page'])]
        path.write_text(json.dumps(units,ensure_ascii=False,indent=2))
        path.with_name('full.txt').write_text('\n\n'.join('['+u['locator']+']\n'+u['text'] for u in units))
        item['text_chars']=sum(u['chars'] for u in units)
        item['low_text_units']=[u['locator'] for u in units if u['chars']<60]
        item['method']='apple_vision_ocr';item['numerical_rules_require_visual_check']=True
    else:item['method']='native_text_or_docx_xml'
    item['review']='indexed_not_all_pages_manually_reviewed'
(root/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
db=sqlite3.connect(root/'search.sqlite3')
db.execute('DROP TABLE IF EXISTS units')
db.execute('CREATE VIRTUAL TABLE units USING fts5(source UNINDEXED, title UNINDEXED, locator UNINDEXED, method UNINDEXED, text, tokenize="unicode61")')
count=0
for item in catalog:
    units=json.loads((root/'extracted'/item['id']/'units.json').read_text())
    for u in units:
        # Keep whitespace normalization in the index only; source text is retained.
        text=re.sub(r'\s+',' ',u['text']).strip()
        if not text:continue
        db.execute('INSERT INTO units VALUES (?,?,?,?,?)',(item['id'],item['file'],u['locator'],u['method'],text));count+=1
db.commit();db.close()
print(json.dumps({'sources':len(catalog),'pdf_pages':sum(x['units'] for x in catalog if x['file'].endswith('.pdf')),'docx_units':sum(x['units'] for x in catalog if x['file'].endswith('.docx')),'indexed_nonempty_units':count},ensure_ascii=False))

"""Local, read-only source extraction with stable page/paragraph provenance."""
import hashlib,json
from pathlib import Path
from pypdf import PdfReader
from docx import Document

root=Path(__file__).resolve().parents[1]/'data/book-library'
catalog=[]
for source in sorted((root/'originals').glob('*')):
    if source.suffix.lower() not in ('.pdf','.docx'):continue
    sid=hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    out=root/'extracted'/sid;out.mkdir(parents=True,exist_ok=True)
    records=[]
    if source.suffix.lower()=='.pdf':
        reader=PdfReader(source)
        for i,p in enumerate(reader.pages,1):
            text=(p.extract_text() or '').replace('\x00',' ')
            records.append({'locator':f'pdf_page:{i}','text':text,'method':'pdf_text','chars':len(text.strip())})
    else:
        doc=Document(source)
        for i,p in enumerate(doc.paragraphs,1):
            records.append({'locator':f'paragraph:{i}','text':p.text,'method':'docx_xml','chars':len(p.text.strip())})
        for i,table in enumerate(doc.tables,1):
            text='\n'.join(' | '.join(c.text for c in row.cells) for row in table.rows)
            records.append({'locator':f'table:{i}','text':text,'method':'docx_xml','chars':len(text.strip())})
    (out/'units.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    (out/'full.txt').write_text('\n\n'.join(f'[{r["locator"]}]\n{r["text"]}' for r in records))
    item={'id':sid,'file':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'units':len(records),'text_chars':sum(r['chars'] for r in records),'low_text_units':[r['locator'] for r in records if r['chars']<60],'extraction':'complete','review':'not_equivalent_to_full_reading'}
    catalog.append(item);print(json.dumps({k:v for k,v in item.items() if k!='low_text_units'},ensure_ascii=False),flush=True)
(root/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))

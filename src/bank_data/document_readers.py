"""Local document readers. Text positions refer to the native extracted text."""
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


def blank_raster(pixmap):
    pixels=pixmap.samples
    return bool(pixels) and pixels.count(255)==len(pixels)


def text_fragments(value,maximum=2000,overlap=160):
    start=0
    while start<len(value):
        end=min(len(value),start+maximum)
        yield start,end,value[start:end]
        if end==len(value):break
        start=end-overlap


def paragraphs(values,sheet,kind,extra=None):
    ordinal=0
    for block,value in enumerate(values,1):
        if not value.strip():continue
        for start,end,fragment in text_fragments(value):
            ordinal+=1
            yield sheet,ordinal,{'__text__':fragment},{'source_kind':kind,'block':block,
                'char_start':start,'char_end':end,'unstructured_text':True,**(extra or {})}


def document_records(path,kind):
    from .readers import table_records
    if kind=='pdf':
        import pymupdf
        with pymupdf.open(str(path)) as document:
            if document.needs_pass:raise ValueError('Encrypted PDF requires review')
            for page_number,page in enumerate(document,1):
                blocks=page.get_text('blocks',sort=True)
                text_blocks=[b for b in blocks if len(b)>6 and b[6]==0 and b[4].strip()]
                if not text_blocks:
                    if blank_raster(page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False)):continue
                    raise ValueError('OCR_REQUIRED: native text absent on page '+str(page_number))
                boxes=[]
                try:tables=page.find_tables().tables
                except Exception:tables=[]
                for index,table in enumerate(tables,1):
                    matrix=table.extract()
                    if len(matrix)<2:continue
                    boxes.append(table.bbox)
                    for sheet,row,cells,context in table_records(iter(matrix),f'page_{page_number}/table_{index}',pad_missing=True):
                        yield sheet,row,cells,{**context,'source_kind':'pdf_table','page':page_number,'bbox':list(table.bbox)}
                for index,block in enumerate(text_blocks,1):
                    x0,y0,x1,y1,text,*_=block
                    if any(x0>=a-1 and y0>=b-1 and x1<=c+1 and y1<=d+1 for a,b,c,d in boxes):continue
                    for sheet,row,cells,context in paragraphs([text],f'page_{page_number}/text','pdf_native_text',
                        {'page':page_number,'pdf_block':index,'bbox':[x0,y0,x1,y1]}):yield sheet,index*10000+row,cells,context
    elif kind=='docx':
        from defusedxml.ElementTree import fromstring
        ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        with zipfile.ZipFile(path) as archive:
            info=archive.getinfo('word/document.xml')
            if info.file_size>64*1024*1024:raise ValueError('DOCX XML exceeds bounded reader size')
            root=fromstring(archive.read(info))
        body=root.find(ns+'body');table_index=0;values=[]
        if body is None:raise ValueError('DOCX body missing')
        for child in body:
            if child.tag==ns+'tbl':
                table_index+=1;matrix=[]
                for tr in child.findall(ns+'tr'):
                    matrix.append(['\n'.join(''.join(p.itertext()) for p in tc.findall(ns+'p')) for tc in tr.findall(ns+'tc')])
                for sheet,row,cells,context in table_records(iter(matrix),f'table_{table_index}',pad_missing=True):
                    yield sheet,row,cells,{**context,'source_kind':'docx_table'}
            elif child.tag==ns+'p':values.append(''.join(child.itertext()))
        yield from paragraphs(values,'paragraphs','docx_native_text')
    elif kind=='legacy_word':
        executable=os.environ.get('BANK_ANTIWORD') or shutil.which('antiword')
        if not executable:raise ValueError('LEGACY_WORD_TOOL_UNAVAILABLE')
        environment=dict(os.environ)
        home=os.environ.get('BANK_ANTIWORD_HOME')
        if home:environment['ANTIWORDHOME']=home
        result=subprocess.run([executable,'-m','UTF-8.txt','-w','0',str(path)],capture_output=True,timeout=90,env=environment)
        if result.returncode:raise ValueError('Legacy Word conversion failed')
        text=result.stdout.decode('utf-8')
        if not text.strip():raise ValueError('Legacy Word native text is empty')
        yield from paragraphs(text.split('\n\n'),'paragraphs','antiword_native_text')
    elif kind in ('txt','text'):
        from .readers import encoding_for
        with path.open(encoding=encoding_for(path)) as stream:
            yield from paragraphs(stream,'lines','plain_text')
    elif kind=='html':
        from html.parser import HTMLParser
        from .readers import encoding_for
        class Tables(HTMLParser):
            def __init__(self):super().__init__();self.tables=[];self.rows=None;self.row=None;self.cell=None
            def handle_starttag(self,tag,attrs):
                if tag=='table':self.rows=[]
                elif tag=='tr' and self.rows is not None:self.row=[]
                elif tag in ('td','th') and self.row is not None:self.cell=[]
            def handle_data(self,data):
                if self.cell is not None:self.cell.append(data)
            def handle_endtag(self,tag):
                if tag in ('td','th') and self.cell is not None:self.row.append(''.join(self.cell));self.cell=None
                elif tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
                elif tag=='table' and self.rows is not None:self.tables.append(self.rows);self.rows=None
        parser=Tables();parser.feed(path.read_text(encoding=encoding_for(path)))
        if not parser.tables:raise ValueError('HTML_WITHOUT_DATA_TABLE: possible download error page')
        for i,rows in enumerate(parser.tables,1):yield from table_records(iter(rows),f'html_table_{i}',pad_missing=True)
    else:raise ValueError('Unsupported document kind')

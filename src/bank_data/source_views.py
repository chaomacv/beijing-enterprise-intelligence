"""Reconstructible HTML text views; original source cells remain unchanged."""
from functools import lru_cache
import hashlib
from html.parser import HTMLParser
import re

VERSION='html-text-and-nonpresentation-attributes-v1'
PREFIX='__html_text__::'
PRESENTATION={'style','class','width','height','align','valign','bgcolor','border','cellspacing','cellpadding','face','size','color','lang','dir','xmlns'}
BLOCKS={'p','div','tr','li','br','h1','h2','h3','h4','h5','h6','table','section','article','dl','dt','dd'}


def looks_html(value):
    return isinstance(value,str) and len(re.findall(r'</?(?:html|body|p|span|div|table|tr|td|th|br|a|ul|ol|li|h[1-6])\b',value,re.IGNORECASE))>=2


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.attributes=[];self.seen=set();self.style_depth=0;self.omitted_style_chars=0;self.omitted_attribute_chars=0

    def handle_starttag(self,tag,attrs):
        if tag=='style':self.style_depth+=1
        if tag in BLOCKS:self.parts.append('\n')
        elif tag in {'td','th'}:self.parts.append('\t')
        for key,value in attrs:
            if value is None:continue
            if key in PRESENTATION or key.startswith('on'):
                self.omitted_attribute_chars+=len(value);continue
            item=(tag,key,value)
            if item not in self.seen:self.seen.add(item);self.attributes.append(item)

    def handle_endtag(self,tag):
        if tag=='style' and self.style_depth:self.style_depth-=1
        if tag in BLOCKS:self.parts.append('\n')

    def handle_data(self,data):
        if self.style_depth:self.omitted_style_chars+=len(data)
        else:self.parts.append(data)

    def handle_comment(self,data):
        # Comments and script text can contain business payloads; keep them as data.
        self.parts.extend(['\n[HTML注释]\n',data,'\n'])


@lru_cache(maxsize=128)
def html_view(value):
    parser=TextParser();parser.feed(value);parser.close()
    body='\n'.join(line.strip() for line in ''.join(parser.parts).replace('\xa0',' ').splitlines() if line.strip())
    if parser.attributes:body+='\n[HTML属性]\n'+'\n'.join(tag+' '+key+'='+value for tag,key,value in parser.attributes)
    return body,parser.omitted_style_chars,parser.omitted_attribute_chars


def source_cell(cells,field):
    if not isinstance(field,str):raise KeyError('Non-string source field')
    if field in cells:return cells[field]
    if field.startswith(PREFIX):
        original=field[len(PREFIX):]
        if original in cells and looks_html(cells[original]):return html_view(cells[original])[0]
    raise KeyError(field)


def project_records(records):
    projected=[];all_views={}
    for row in records:
        cells={};views=[]
        for field,value in row['cells'].items():
            if field.startswith(PREFIX) or not looks_html(value):cells[field]=value;continue
            target=PREFIX+field
            if target in row['cells']:raise ValueError('Reserved HTML view field collides with a source column')
            view,style_chars,attribute_chars=html_view(value);cells[target]=view
            views.append({'source_field':field,'view_field':target,'version':VERSION,
                'source_sha256':hashlib.sha256(value.encode('utf-8')).hexdigest(),'source_chars':len(value),'view_chars':len(view),
                'presentation_style_chars_omitted_from_model':style_chars,'presentation_attribute_chars_omitted_from_model':attribute_chars})
        if views:
            all_views[row['record_id']]=views
            projected.append({**row,'cells':cells,'context':{**row.get('context',{}),'input_field_views':views}})
        else:projected.append(row)
    return projected,all_views

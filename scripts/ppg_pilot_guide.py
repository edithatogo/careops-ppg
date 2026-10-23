"""Render the operator supplement using qualified links supplied outside Git."""
import html
from urllib.parse import urlsplit


def render(definition, bindings):
    required={link['key'] for section in definition['sections'] for link in section['links']}
    if required-set(bindings): raise ValueError('Missing qualified guide links')
    for key in required:
        uri=urlsplit(bindings[key])
        if uri.scheme!='https' or not uri.netloc or uri.username or uri.password:
            raise ValueError('Unsafe guide link')
    if definition['clinicalApproval'] is not False or definition['notificationsEnabled'] is not False:
        raise ValueError('Guide must not confer approval or sending')
    esc=html.escape
    parts=['<p>Guide '+esc(definition['guideVersion'])+' — qualification snapshot '+esc(definition['asOf'])+'.</p>',
           '<h2>'+esc(definition['title'])+'</h2>',
           '<p><strong>Subject:</strong> '+esc(definition['subject'])+'</p>',
           '<p><strong>'+esc(definition['notice'])+'</strong></p>',
           '<p>Linked records may change after this snapshot. Inspect their current version and evidence before acting.</p>']
    for s in definition['sections']:
        parts+=['<h3>'+esc(s['title'])+'</h3>', '<p><strong>When:</strong> '+esc(s['trigger'])+'</p>',
                '<ol>'+''.join('<li>'+esc(step)+'</li>' for step in s['steps'])+'</ol>',
                '<ul>'+''.join('<li><a href="'+esc(bindings[l['key']],quote=True)+'">'+esc(l['label'])+'</a></li>' for l in s['links'])+'</ul>',
                '<p><strong>Boundary:</strong> '+esc(s['hold'])+'</p>']
    return '\n'.join(parts)

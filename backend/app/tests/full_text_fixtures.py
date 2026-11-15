"""Synthetic scholarly HTML; no external downloads or provider calls."""
PROSE = (
    'Participants were allocated to the study groups using the prespecified protocol. '
    'Measurements were collected at scheduled visits and evaluated against baseline. '
    'The investigators recorded outcomes and uncertainty for each comparison. '
)
FULL_TEXT_HTML = (
    '<html><body><article><h1>Controlled study</h1><h2>Abstract</h2><p>Study summary.</p>'
    + ''.join(f'<h2>{heading}</h2><p>{PROSE}</p>' for heading in ('Introduction', 'Methods', 'Results', 'Discussion'))
    + '<h2>References</h2><p>Bibliography.</p></article></body></html>'
).encode()
LANDING_HTML = (
    '<html><body><article><h1>Repository record</h1><h2>Abstract</h2><p>'
    + PROSE * 8 + '</p></article><footer>Repository navigation</footer></body></html>'
).encode()

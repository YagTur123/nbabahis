import unicodedata
import re
from datetime import datetime

ALIASES = {
    'nic claxton': 'nicolas claxton',
    'cam thomas': 'cameron thomas',
    'p j washington': 'pj washington',
    'p.j. washington': 'pj washington',
    'penny hardaway': 'anfernee hardaway',
    'patty mills': 'patrick mills',
    'ish smith': 'ishmael smith',
    'mitch robinson': 'mitchell robinson',
    'mo bamba': 'mohamed bamba',
    'gabe vincent': 'gabriel vincent',
    'cam johnson': 'cameron johnson',
    'fred vanvleet': 'fred van vleet',
    'herb jones': 'herbert jones',
    'guenther': 'gunther',
    'og anunoby': 'o.g. anunoby',
}

def _norm_name(name: str) -> str:
    if not name: return ""
    # Normalize unicode to ASCII
    n = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    # Basic cleaning
    n = n.lower().replace('.', ' ').replace('-', ' ')
    n = re.sub(r"[^a-z ]", "", n)
    # Remove common suffixes (jr, sr, iii, iv, ii)
    n = re.sub(r"\b(jr|sr|iii|iv|ii)\b", "", n)
    # Normalize spacing
    n = " ".join(n.split())
    # Alias lookup
    return ALIASES.get(n, n)
def seasons(date_str: str):
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    y = dt.year
    if dt.month >= 9:
        return f"{y}-{str(y+1)[-2:]}", f"{y-1}-{str(y)[-2:]}"
    return f"{y-1}-{str(y)[-2:]}", f"{y-2}-{str(y-1)[-2:]}"

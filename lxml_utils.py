"""
lxml_util.py
Handy functions when using lxml.

NB. used with python2.5. Some methods of
    cgi are deprecated into urlparse.
"""

import time
import re
import os.path
import urlparse, urllib
import cgi
import htmlentitydefs
import lxml.etree

#
# Patterns
#
price_pat = re.compile(r'\$?([\d,]+(\.\d\d)?)')
space_pat = re.compile(r'\s+')

#
# Regex helpers
#

def rgx1(pat, s):
    """ Takes a pattern and a string.  Returns match.group(1) or None. """
    match = pat.search(s)
    if not match:
        return
    return match.group(1)

def rgx_tup(pat, s):
    """ Takes a pattern and a string.  Returns match.groups() or None. """
    match = pat.search(s)
    if not match:
        return
    return match.groups()

def get_jsvar_pat(varname):
    """
    Given a variable name, returns a pattern matching the variable's
    value if it exists.
    NOTE: the variable name must escape its own characters if necessary
     """
    return re.compile('%s\s*=\s*["\']([^"\']+)["\']' % varname)

#
# URL processors
#
def _filter_urldict(urldict, valid_args, case_sensitive=True):
    """
    Common helper for filtering a URL dict down to those keys found in
    valid_args.  Does case-insensitive comparison if case_sensitive = False.

    NB: This function does not return a dict, but a sorted list of (key, value)
    pairs.
    """
    newdict = {}
    if not case_sensitive:
        lcasemap = dict([(key.lower(), key) for key in urldict])

    for key in valid_args:
        if key in urldict:
            newdict[key] = urldict[key][0]
        elif not case_sensitive:
            if key.lower() in lcasemap:
                othercase_key = lcasemap[key.lower()]
                newdict[othercase_key] = urldict[othercase_key][0]
    return [(k, newdict[k]) for k in sorted(newdict.keys())]

def filter_url_qs(url, valid_args, attr='query', case_sensitive=True):
    """
    Takes a url and a list of valid arguments for its query string.
    Returns a URL whose query string only contains the valid arguments.

    If case_sensitive is False, URL normalization will case insensitive.
    """
    u = urlparse.urlparse(url)
    urldict = cgi.parse_qs(getattr(u, attr))
    newpairs = _filter_urldict(urldict, valid_args,
        case_sensitive=case_sensitive)
    udict = {attr: urllib.urlencode(newpairs)}
    normed_url = urlparse.urlunparse( (u.scheme, u.netloc, u.path,
        '', # the mystical "params" component
        udict.get('query', ''),
        udict.get('fragment', '')
        ) )
    return normed_url

def filter_multi_url_qs(url, arg_tups, attr='query', case_sensitive=True):
    """
    Takes a url and a list of (leading_arg, (extra_args)) tuples for its
    query string.  Returns a URL whose query string only contains
    arguments described by arg_tups.  Specifically, this function
    iterates through arg_tups, and...

        1) If leading_arg is in the query string, reduce the URL down to the
           variable names in (extra_args), then stop iteration.

        2) Else, continue iterating until the list ends or a match is
           found.

    If attr == 'fragment', the URL fragment will be used instead of the
    URL query string.
    """
    u = urlparse.urlparse(url)
    urldict = cgi.parse_qs(getattr(u, attr))
    newpairs = None
    for leadkey, subkeys in arg_tups:
        if leadkey in urldict:
            newpairs = _filter_urldict(urldict, [leadkey] + list(subkeys),
                case_sensitive=case_sensitive)
            break
    if newpairs is None:
        newpairs = [(k, urldict[k]) for k in sorted(urldict.keys())]
    udict = {attr: urllib.urlencode(newpairs)}
    normed_url = urlparse.urlunparse( (u.scheme, u.netloc, u.path,
        '', # params
        udict.get('query', ''),
        udict.get('fragment', '')
        ) )
    return normed_url

def link_to_qsdict(url, attr='query'):
    """
    Takes a complete URL.  Returns a dict-representation of the query string
    (or the 'fragment' if attr='fragment').
    NB: each value in the dict will be a list.
    """
    return cgi.parse_qs(
        getattr(urlparse.urlparse(url), attr))

def link_to_dict(url, attr='query'):
    """
    Takes a complete URL.  Returns a dict-representation of the query string
    (or the 'fragment' if attr='fragment'), like link_to_qsdict, but flattens
    out single-item lists into items.  I.e., {'productID' : '3939'} instead of
    {'productID' : ['3939']}.
    """
    qsdict = link_to_qsdict(url, attr=attr)
    for key in qsdict:
        if len(qsdict[key]) == 1:
            qsdict[key] = qsdict[key][0]
    return qsdict

#
# Text helpers
#

def trim_spaces(s):
    """
    Converts one or more spaces in a string to one, throughout the string.
    """
    if isinstance(s, unicode):
        # replace nonbreaking spaces with spaces
        s = s.replace(u'\xa0', u' ')
    return space_pat.sub(' ', s)

def normalize_price(p):
    """
    Takes a price string like $4.50 and returns '4.50' [Could be
    extended for things like €2,50.]
    """
    if len(p) > 0 and p[0] in ('$',):
        p = p[1:]
    return p

def min_price_in(s):
    """
    Takes a string with one or more prices in it. Returns the lowest of those
    prices.
    """
    try:
        pricestrs = (match.group(1).replace(',', '') for match in
            price_pat.finditer(s))
        num, price = min((float(s), s) for s in pricestrs) # Could use Decimal, but it's slow
    except ValueError:
        return None
    return price

def gen_breadcrumbed_names(cat_names):
    """
    Takes a sequence of top-down category names, e.g:

        ['Womens', 'Dresses', 'Printed']

    and converts them to:

        ['Womens', 'Womens > Dresses', 'Womens > Dresses > Printed']
    """
    base = ''
    for cat_name in cat_names:
        yield base + cat_name
        base = base + cat_name + ' > '


def unescape_entities(text):
    """
    Removes HTML or XML character references and entities from a text string.

    @param text The HTML (or XML) source text.
    @return The plain text, as a Unicode string, if necessary.

    Author: Fredrik Lundh, 10/28/2006
    Source: http://effbot.org/zone/re-sub.htm#unescape-html
    """

    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)

def fix_entities(text):
    """
    Replaces unicode characters from invalid HTML entities (such as
    &#153; for &trade;) with HTML entities.

    A more complete solution will be to do this for all Windows-1252
    entities listed under cp1252 at:
    http://www.gnome.org/~jdub/bzr/planet/2.0/planet/feedparser.py
    """
    mappings = ( (u'\x99', u'\u2122'),  # &#153; -> trademark symbol
                 (u'\u02da', u'\00b0'), # &#730; -> degree symbol
                 (u'\x9d', '')          # question mark diamond control symbol?
                )
    if isinstance(text, unicode):
        for bad, good in mappings:
            text = text.replace(bad, good)
    return text

def ensure_latin1(s):
    """
    Takes a string/unicode string and ensures that it can convert to
    latin1. If necessary, it will clean it up by:

        #. removing trademark symbols (which are not in latin1)
        #. converting curly apostrophes to ascii apostrophes
        #. coverting en dash to ascii dash

    NB: This function *will fail by design* when given a raw string that
    cannot be decoded to unicode.
    """
    try:
        s.encode('latin1')
    except UnicodeEncodeError:
        s = s.replace(u'\u2122', '')
        s = s.replace(u'\u2019', "'")
        s = s.replace(u'\u2013', '-')
        s.encode('latin1')
    return s

#
# LXML helpers
#
def is_text_lx(el):
    """
    Returns False if an element is a comment or processing instruction
    (<!-- or <?)
    """
    return (el.tag is not lxml.etree.Comment and
        el.tag is not lxml.etree.ProcessingInstruction)

def lx_to_all_text(el):
    bits = []
    """
    Takes an LXML element.  Returns all containing text including comments or JS
    with no alterations.
    """
    for child in el.iter():
        if child.tag == 'br':
            assert not child.text
            bits.append('\n')
        if child.text:
            bits.append(child.text)
        if child.tail and child is not el:
            # the first item returned by el.iter() is el, but we don't want
            # to include whatever text came after el.iter
            bits.append(child.tail)
    return ''.join(bits)

def lx_to_text(el):
    """
    Takes an LXML element.  Returns all containing text, but no comments or JS.
    """
    bits = []
    for child in el.iter():
        if not is_text_lx(child):
            continue # skip comments
        if child.tag == 'script':
            continue # skip script tags
        if child.tag == 'br':
            assert not child.text
            bits.append('\n')
        if child.text:
            bits.append(child.text)
        if child.tail and child is not el:
            # the first item returned by el.iter() is el, but we don't want
            # to include whatever text came after el.iter
            bits.append(child.tail)
    trimmed = trim_spaces(''.join(bits))
    return trimmed.strip()

def lx_to_topmost_text(el):
    """
    Takes an LXML element.  Returns only its text nodes (i.e.
    el.text and the tail of all children.
    """
    bits = [child.tail for child in el if child.tail]
    if el.text and is_text_lx(el):
        bits.insert(0, el.text)
    trimmed = trim_spaces(''.join(bits))
    return trimmed.strip()

def select_one(selector, lx, assert_one=True):
    """
    Calls selector with lx, asserts that the result is a list with one item,
    and returns that item.
    """
    items = selector(lx)
    if assert_one:
        assert len(items) == 1, "%s found %d items, not 1" % (
            selector.css, len(items))
    if len(items) > 0:
        return items[0]


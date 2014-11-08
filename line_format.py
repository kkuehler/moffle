import re

import cachetools
from flask import url_for

import util

CTRL_COLOR = '\x03'      # ^C = color
CTRL_RESET = '\x0F'      # ^O = reset
CTRL_UNDERLINE = '\x1F'  # ^_ = underline
CTRL_BOLD = '\x02'       # ^B = bold

CTRL_REGEX = re.compile(r'(?:[%s%s%s])|(%s(?:\d{1,2}),?(?:\d{1,2})?)' % (
    CTRL_RESET,
    CTRL_UNDERLINE,
    CTRL_BOLD,
    CTRL_COLOR))


def ctrl_to_colors(text):
    # the first character is CTRL_COLOR
    colors = text[1:].split(',')

    # People who spam the color changer without any color code
    # ruin it for the rest of us.

    if len(text) == 1:
        fg_color_id = None
        bg_color_id = None
    elif len(colors) == 1:
        fg_color_id = int(colors[0])
        bg_color_id = None
    else:
        fg_color_id = int(colors[0])
        bg_color_id = int(colors[1])
    return (fg_color_id, bg_color_id)


class LineState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.fg_color = None
        self.bg_color = None
        self.bold = False
        self.underline = False

    def toggle_bold(self):
        self.bold = not self.bold

    def toggle_underline(self):
        self.underline = not self.underline

    def set_color(self, fg_color_id=None, bg_color_id=None):
        self.fg_color = fg_color_id
        if bg_color_id is not None:
            self.bg_color = bg_color_id


def generate_span(state):
    classes = []
    if state.bold:
        classes.append('irc-bold')
    if state.underline:
        classes.append('irc-underline')

    # we don't display colors higher than 15
    if state.fg_color is not None and state.fg_color < 16:
        classes.append("irc-fg-%s" % state.fg_color)
    if state.bg_color is not None and state.fg_color < 16:
        classes.append("irc-bg-%s" % state.bg_color)
    return "<span class=\"%s\">" % ' '.join(classes)


# Don't ask me why the filter name is different from the function name.
@util.delay_template_filter('control_codes')
@cachetools.lru_cache(maxsize=16384)
def irc_format(text, autoescape=None):
    result = ''

    # split text into fragments that are either plain text
    # or a control code sequence
    text = CTRL_REGEX.sub("\n\g<0>\n", text)
    fragments = text.split("\n")

    line_state = LineState()
    is_inside_span = False
    for fragment in fragments:
        if not fragment:
            # for blank fragments
            continue

        first_char = fragment[0]

        was_control_code = True
        if first_char == CTRL_COLOR:
            (fg_color_id, bg_color_id) = ctrl_to_colors(fragment)
            line_state.set_color(fg_color_id, bg_color_id)
        elif first_char == CTRL_RESET:
            line_state.reset()
        elif first_char == CTRL_UNDERLINE:
            line_state.toggle_underline()
        elif first_char == CTRL_BOLD:
            line_state.toggle_bold()
        else:
            was_control_code = False

        if was_control_code:
            to_concat = ''
            if is_inside_span:
                to_concat = "</span>"

            span = generate_span(line_state)
            to_concat = "%s%s" % (to_concat, span)
            is_inside_span = True
        else:
            to_concat = fragment

        result = "%s%s" % (result, to_concat)
    if is_inside_span:
        result = "%s</span>" % result

    return result


@cachetools.lru_cache(maxsize=16384)
def _lenient_prefix(haystack, needle):
    try:
        return haystack.index(needle) == 0
    except ValueError:
        return False


@util.delay_template_filter('line_style')
@cachetools.lru_cache(maxsize=16384)
def line_style(s, line_no, is_search, network=None, ctx=None):
    """
    ctx is a grep Line object. Yes, I know it's duplicating s and line_no.
    Deal with it.
    """
    timestamp, rest = s.split(' ', 1)

    classes = []

    if ctx and ctx.line_marker == ':':
        classes.append("irc-highlight")

    if _lenient_prefix(rest, "*** Quits"):
        classes.append("irc-part")

    if _lenient_prefix(rest, "*** Joins"):
        classes.append("irc-join")

    # Make links back to actual line if we're in search.
    if is_search:
        href = url_for(
            'log',
            network=network,
            channel=ctx.channel,
            date=ctx.date,
            _anchor='L{}'.format(line_no),
        )
        id_ = ''
    else:
        href = '#L{}'.format(line_no)
        id_ = 'L{}'.format(line_no)

    return '<span class="{class_}">' \
        '<a href="{href}" id="{id_}" class="js-line-no-highlight">{timestamp}</a> ' \
        '{rest}</span>' \
        .format(
        class_=' '.join(classes),
        timestamp=timestamp,
        href=href,
        id_=id_,
        rest=rest,
    )

# coding: utf8

#  WeasyPrint converts web documents (HTML, CSS, ...) to PDF.
#  Copyright (C) 2011  Simon Sapin
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as
#  published by the Free Software Foundation, either version 3 of the
#  License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.


from .markers import image_marker_layout
from .percentages import resolve_percentages
from .. import text
from ..formatting_structure import boxes
from ..css.values import get_single_keyword

TEXT_FRAGMENT = text.TextLineFragment()

class InlineContext(object):
    def __init__(self, linebox, page_bottom):
        self.linebox = linebox
        self.page_bottom = page_bottom
        self.position_y = linebox.position_y
        self.position_x = linebox.position_x
        self.containing_block_width = linebox.containing_block_size()[0]
        self.save()

    def save(self):
        self._linebox = self.linebox.copy()
        self._position_y = self.position_y

    def restore(self):
        self.linebox = self._linebox.copy()
        self.position_y = self._position_y

    def lines(self):
        for line in breaking_linebox(self.linebox, self.containing_block_width):
            white_space_processing(line)
            compute_linebox_dimensions(line)
            compute_linebox_positions(line, self.position_x, self.position_y)
            vertical_align_processing(line)
            if not is_empty_line(line):
                self.position_y += line.height
                if self.page_bottom > self.position_y:
                    self.save()
                    yield line
                else:
                    self.restore()
                    break


def get_new_lineboxes(linebox, page_bottom):
    inline_context = InlineContext(linebox, page_bottom)
    return inline_context.lines()

def inline_replaced_box_layout(box):
    """Create the layout for an inline :class:`boxes.ReplacedBox` object."""
    assert isinstance(box, boxes.ReplacedBox)
    resolve_percentages(box)

    # Compute width
    if box.margin_left == 'auto':
        box.margin_left = 0
    if box.margin_right == 'auto':
        box.margin_right = 0

    intrinsic_ratio = box.replacement.intrinsic_ratio()
    intrinsic_height = box.replacement.intrinsic_height()
    intrinsic_width = box.replacement.intrinsic_width()

    if box.width == 'auto':
        if intrinsic_width is not None:
            box.width = intrinsic_width
        elif intrinsic_height is not None and intrinsic_ratio is not None:
            box.width = intrinsic_ratio * intrinsic_height
        else:
            raise NotImplementedError
            # Then the used value of 'width' becomes 300px. If 300px is too
            # wide to fit the device, UAs should use the width of the largest
            # rectangle that has a 2:1 ratio and fits the device instead.

    # Compute height
    if box.margin_top == 'auto':
        box.margin_top = 0
    if box.margin_bottom == 'auto':
        box.margin_bottom = 0

    if box.height == 'auto' and box.width == 'auto':
        if intrinsic_height is not None:
            box.height = intrinsic_height
    elif intrinsic_ratio is not None and box.height == 'auto':
        box.height = box.width / intrinsic_ratio
    else:
        raise NotImplementedError
        # Then the used value of 'height' must be set to the height of
        # the largest rectangle that has a 2:1 ratio, has a height not
        # greater than 150px, and has a width not greater than the
        # device width.


# Dimensions

def compute_linebox_dimensions(linebox):
    """Compute the height of the linebox """
    assert isinstance(linebox, boxes.LineBox)
    heights = [0]
    widths = [0]
    for child in linebox.children:
        widths.append(child.width)
        heights.append(child.height)
    linebox.width = sum(widths)
    linebox.height = max(heights)


def compute_inlinebox_dimensions(inlinebox):
    resolve_percentages(inlinebox)
    widths = [0]
    heights = [0]
    for child in inlinebox.children:
        widths.append(child.margin_width())
        heights.append(child.height)
    inlinebox.width = sum(widths)
    inlinebox.height = max(heights)


def compute_textbox_dimensions(textbox):
    assert isinstance(textbox, boxes.TextBox)
    TEXT_FRAGMENT.set_textbox(textbox)
    textbox.width, textbox.height = TEXT_FRAGMENT.get_size()
    textbox.baseline = TEXT_FRAGMENT.get_baseline()


def compute_atomicbox_dimensions(box):
    assert isinstance(box, boxes.AtomicInlineLevelBox)
    if isinstance(box, boxes.ImageMarkerBox):
        image_marker_layout(box)
    if isinstance(box, boxes.ReplacedBox):
        inline_replaced_box_layout(box)
    else:
        raise TypeError('Layout for %s not handled yet' % type(box).__name__)


def compute_linebox_positions(linebox,ref_x, ref_y):
    assert isinstance(linebox, boxes.LineBox)
    # Linebox have no margin/padding/border
    linebox.position_x = ref_x
    linebox.position_y = ref_y
    for child in linebox.children:
        if isinstance(child, boxes.InlineBox):
            compute_inlinebox_positions(child,ref_x, ref_y)
        elif isinstance(child, boxes.AtomicInlineLevelBox):
            compute_atomicbox_positions(child, ref_x, ref_y)
        elif isinstance(child, boxes.TextBox):
            compute_textbox_positions(child, ref_x, ref_y)
        ref_x += child.margin_width()


def compute_inlinebox_positions(box,ref_x, ref_y):
    assert isinstance(box, boxes.InlineBox)
    box.position_x = ref_x
    ignored_height = box.padding_top + box.border_top_width + box.margin_top
    box.position_y = ref_y - ignored_height
    inline_ref_y = box.position_y
    inline_ref_x = box.content_box_x()
    for child in box.children:
        if isinstance(child, boxes.InlineBox):
            compute_inlinebox_positions(child, inline_ref_x, inline_ref_y)
        elif isinstance(child, boxes.AtomicInlineLevelBox):
            compute_atomicbox_positions(child, inline_ref_x, inline_ref_y)
        elif isinstance(child, boxes.TextBox):
            compute_textbox_positions(child, inline_ref_x, inline_ref_y)
        inline_ref_x += child.margin_width()


def compute_textbox_positions(box,ref_x, ref_y):
    assert isinstance(box, boxes.TextBox)
    box.position_x = ref_x
    box.position_y = ref_y


def compute_atomicbox_positions(box,ref_x, ref_y):
    assert isinstance(box, boxes.AtomicInlineLevelBox)
    box.translate(ref_x, ref_y)


def is_empty_line(linebox):
    #TODO: complete this function
    if len(linebox.children) == 0:
        return linebox
    text = ""
    len_textbox = 0
    for child in linebox.descendants():
        if isinstance(child, boxes.TextBox):
            len_textbox += 1
            text += child.text.strip(" ")
    return text == "" and len_textbox == len(linebox.children)


def get_new_empty_line(linebox):
    """Return empty copy of `linebox`"""
    new_line = linebox.copy()
    new_line.empty()
    new_line.width = 0
    new_line.height = 0
    return new_line


def breaking_linebox(linebox, allocate_width):
    """
    Cut the `linebox` and return lineboxes that have a width greater than
    allocate_width
    Eg.

    LineBox[
        InlineBox[
            TextBox('Hello.'),
        ],
        InlineBox[
            InlineBox[TextBox('Word :D')],
            TextBox('This is a long long long text'),
        ]
    ]
    is turned into
    [
        LineBox[
            InlineBox[
                TextBox('Hello.'),
            ],
            InlineBox[
                InlineBox[TextBox('Word :D')],
                TextBox('This is a long'),
            ]
        ], LineBox[
            InlineBox[
                TextBox(' long long text'),
            ]
        ]
    ]
    """
    new_line = get_new_empty_line(linebox)
    while linebox.children:
        if not new_line.children:
            width = allocate_width
        child = linebox.children.popleft()
        if isinstance(child, boxes.TextBox):
            part1, part2 = breaking_textbox(child, width)
            compute_textbox_dimensions(part1)
        elif isinstance(child, boxes.InlineBox):
            resolve_percentages(child)
            part1, part2 = breaking_inlinebox(child, width)
            compute_inlinebox_dimensions(part1)
        elif isinstance(child, boxes.AtomicInlineLevelBox):
            part1 = child
            part2 = None
            compute_atomicbox_dimensions(part1)

        if part2:
            linebox.children.appendleft(part2)

        if part1:
            if part1.margin_width() <= width:
                width -= part1.margin_width()
                new_line.add_child(part1)
            else:
                if not new_line.children:
                    new_line.add_child(part1)
                else:
                    linebox.children.appendleft(part1)
                yield new_line
                new_line = get_new_empty_line(linebox)
        else:
            yield new_line
            new_line = get_new_empty_line(linebox)
    yield new_line


def breaking_inlinebox(inlinebox, allocate_width):
    """
    Cut `inlinebox` that sticks out the LineBox if possible

    >>> breaking_inlinebox(inlinebox, allocate_width)
    (first_inlinebox, second_inlinebox)

    Eg.
        InlineBox[
            InlineBox[TextBox('Word :D')],
            TextBox('This is a long long long text'),
        ]
    is turned into
        (
            InlineBox[
                InlineBox[TextBox('Word :D')],
                TextBox('This is a long'),
            ], InlineBox[
                TextBox(' long long text'),
            ]
        )
    """
    left_spacing = inlinebox.padding_left + inlinebox.margin_left + \
                   inlinebox.border_left_width
    right_spacing = inlinebox.padding_right + inlinebox.margin_right + \
                   inlinebox.border_right_width
    allocate_width -= left_spacing
    if allocate_width <= 0:
        return None, inlinebox

    new_inlinebox = inlinebox.copy()
    new_inlinebox.empty()

    while inlinebox.children:
        child = inlinebox.children.popleft()
        # if last child
        last_child = len(inlinebox.children) == 0

        if isinstance(child, boxes.TextBox):
            part1, part2 = breaking_textbox(child, allocate_width)
            compute_textbox_dimensions(part1)
        elif isinstance(child, boxes.InlineBox):
            resolve_percentages(child)
            part1, part2 = breaking_inlinebox(child,allocate_width)
            compute_inlinebox_dimensions(part1)
        elif isinstance(child, boxes.AtomicInlineLevelBox):
            part1 = child
            part2 = None
            compute_atomicbox_dimensions(part1)

        if part2 is not None:
            inlinebox.children.appendleft(part2)

        if part1:
            if part1.margin_width() <= allocate_width:
                # We have enough room to fit `part1` in this line.
                if last_child:
                    if (part1.margin_width() + right_spacing) <= allocate_width:
                        allocate_width -= part1.margin_width()
                        new_inlinebox.add_child(part1)
                        break
                    else:
                        # Enough for `part1` but not `part1` plus the right
                        # padding, border and margin of the parent.
                        if new_inlinebox.children:
                            inlinebox.children.appendleft(part1)
                        else:
                            # `part1` does not fit but the line box
                            # is still empty: overflow
                            # XXX: this is not correct, we should try to break
                            # earlier. This fixes the infinite loop for now.
                            new_inlinebox.add_child(part1)
                        break
                else:
                    allocate_width -= part1.margin_width()
                    new_inlinebox.add_child(part1)
                    if allocate_width == 0:
                        break
            else:
                if new_inlinebox.children:
                    inlinebox.children.appendleft(part1)
                else:
                    # `part1` does not fit but the line box
                    # is still empty: overflow
                    new_inlinebox.add_child(part1)
                break
        else:
            break

    inlinebox.reset_spacing("left")
    if inlinebox.children:
        new_inlinebox.reset_spacing("right")

    if inlinebox.children:
        return new_inlinebox, inlinebox
    else:
        return new_inlinebox, None


def breaking_textbox(textbox, allocate_width):
    """
    Cut the `textbox` that sticks out the LineBox only if `textbox` can be cut
    by a line break

    >>> breaking_textbox(textbox, allocate_width)
    (first_textbox, second_textbox)

    Eg.
        TextBox('This is a long long long long text')
    is turned into

        (
            TextBox('This is a long long'),
            TextBox(' long long text')
        )
    but
        TextBox('Thisisalonglonglonglongtext')
    is turned into
        (
            TextBox('Thisisalonglonglonglongtext'),
            None
        )
    """
    TEXT_FRAGMENT.set_textbox(textbox)
    TEXT_FRAGMENT.set_width(allocate_width)
    # We create a new TextBox with the first part of the cutting text
    first_tb = textbox.copy()
    first_tb.text = TEXT_FRAGMENT.get_text()
    # And we check the remaining text
    second_tb = None
    if TEXT_FRAGMENT.get_remaining_text() != "":
        second_tb = textbox.copy()
        second_tb.text = TEXT_FRAGMENT.get_remaining_text()
    return first_tb, second_tb


def white_space_processing(linebox):
    """Remove first and last white space in `linebox`"""
    def get_first_textbox(linebox):
        for child in linebox.descendants():
            if isinstance(child, boxes.TextBox):
                return child

    def get_last_textbox(linebox):
        last_child = None
        for child in linebox.descendants():
            if isinstance(child, boxes.TextBox):
                last_child = child
        return last_child
    first_textbox = get_first_textbox(linebox)
    last_textbox = get_last_textbox(linebox)
    # If a space (U+0020) at the beginning or the end of a line has
    # 'white-space' set to 'normal', 'nowrap', or 'pre-line', it is removed.
    if first_textbox:
        white_space = get_single_keyword(first_textbox.style.white_space)
        if white_space in ('normal', 'nowrap', 'pre-line'):
            if get_single_keyword(first_textbox.style.direction) == "rtl":
                first_textbox.text = first_textbox.text.rstrip(' \t')
            else:
                first_textbox.text = first_textbox.text.lstrip(' \t')
    if last_textbox:
        white_space = get_single_keyword(last_textbox.style.white_space)
        if white_space in ('normal', 'nowrap', 'pre-line'):
            if get_single_keyword(last_textbox.style.direction) == "rtl":
                last_textbox.text = last_textbox.text.lstrip(' \t')
            else:
                last_textbox.text = last_textbox.text.rstrip(' \t')

    # TODO: All tabs (U+0009) are rendered as a horizontal shift that
    # lines up the start edge of the next glyph with the next tab stop.
    # Tab stops occur at points that are multiples of 8 times the width
    # of a space (U+0020) rendered in the block's font from the block's
    # starting content edge.

    # TODO: If spaces (U+0020) or tabs (U+0009) at the end of a line have
    # 'white-space' set to 'pre-wrap', UAs may visually collapse them.

def compute_baseline_positions(box):
    """Compute the relative position of baseline"""
    positions = [0]
    for child in box.children:
        if isinstance(child, boxes.InlineBox):
            if child.children:
                compute_baseline_positions(child)
            else:
                child.baseline = child.height
            positions.append(child.baseline)
        elif isinstance(child, boxes.AtomicInlineLevelBox):
            child.baseline = child.height
            positions.append(child.height)
        elif isinstance(child, boxes.TextBox):
            positions.append(child.baseline)
    box.baseline = max(positions)


def vertical_align_processing(linebox):
    """compute the real positions of boxes, with vertical-align property"""
    compute_baseline_positions(linebox)
    absolute_baseline = linebox.baseline
    #TODO: implement other properties

    for box in linebox.descendants():
        box.position_y += absolute_baseline - box.baseline

    bottom_positions = [box.position_y+box.height for box in linebox.children]
    linebox.height = max(bottom_positions or [0]) - linebox.position_y
